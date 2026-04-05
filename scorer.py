from __future__ import annotations

import json

import anthropic
import httpx

import config
from scraper import NewsItem
from markets import Market
from utils import retry


client = anthropic.Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    timeout=httpx.Timeout(30.0, connect=10.0),
)

SCORING_PROMPT = """You are a prediction market analyst. Today's date is {current_date}. Your job is to assess whether recent news shifts the probability of a market question resolving YES.

## Market Question
{question}

## Current Market Price
YES token price: {yes_price:.2f} (market's implied probability: {yes_price:.0%})
This price reflects real-time trading conditions as of today. Treat it as the baseline.

## Recent News Headlines (last {lookback}h)
{headlines}

## Instructions
1. The market price above is live and accurate — it reflects current real-world conditions. Do NOT override it with your own knowledge of past prices or events.
2. Analyze each headline for relevance to the market question.
3. Assess whether the news shifts the probability UP or DOWN from the current market price.
4. Only deviate significantly from market price if headlines provide strong, direct evidence.
5. If no headlines are relevant, return the market price as your confidence.

Respond with ONLY valid JSON in this exact format:
{{
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<2-3 sentence explanation>",
  "relevant_headlines": [<indices of relevant headlines, 0-indexed>]
}}"""


@retry(max_attempts=2, base_delay=2.0)
def score_market(market: Market, news: list[NewsItem]) -> dict:
    """Score a market question against recent news using Claude."""
    headlines_text = "\n".join(
        f"[{i}] [{item.source}] ({item.age_hours():.1f}h ago) {item.headline}"
        for i, item in enumerate(news)
    )

    if not headlines_text.strip():
        return {
            "confidence": market.yes_price,
            "reasoning": "No relevant news found — deferring to market price.",
            "relevant_headlines": [],
        }

    from datetime import datetime, timezone
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = SCORING_PROMPT.format(
        question=market.question,
        yes_price=market.yes_price,
        lookback=config.NEWS_LOOKBACK_HOURS,
        headlines=headlines_text,
        current_date=current_date,
    )

    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        return result

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return {
            "confidence": market.yes_price,
            "reasoning": f"Parsing error: {e}",
            "relevant_headlines": [],
        }
    except Exception as e:
        return {
            "confidence": market.yes_price,
            "reasoning": f"Scoring error ({type(e).__name__}): {e}",
            "relevant_headlines": [],
        }


def filter_news_for_market(market: Market, news: list[NewsItem]) -> list[NewsItem]:
    """Quick keyword filter to reduce noise before scoring."""
    keywords = _extract_keywords(market.question)
    if not keywords:
        return news[:30]  # fallback: send top 30 by recency

    relevant = []
    for item in news:
        text = f"{item.headline} {item.summary}".lower()
        if any(kw in text for kw in keywords):
            relevant.append(item)

    return relevant[:30] if relevant else news[:15]


def _extract_keywords(question: str) -> list[str]:
    """Extract meaningful keywords from a market question."""
    stopwords = {
        "will", "the", "a", "an", "be", "by", "in", "on", "at", "to",
        "of", "for", "is", "it", "this", "that", "and", "or", "not",
        "before", "after", "end", "yes", "no", "any", "has", "have",
        "does", "do", "than", "more", "less", "over", "under",
    }
    words = question.lower().split()
    keywords = [w.strip("?.,!") for w in words if w.strip("?.,!") not in stopwords and len(w) > 2]
    return keywords


if __name__ == "__main__":
    from scraper import scrape_all

    test_market = Market(
        condition_id="test",
        question="Will OpenAI release GPT-5 before July 2025?",
        category="ai",
        yes_price=0.35,
        no_price=0.65,
        volume=500000,
        end_date="2025-07-01",
        active=True,
        tokens=[],
    )

    print("Scraping news...")
    news = scrape_all()
    filtered = filter_news_for_market(test_market, news)
    print(f"Found {len(filtered)} relevant headlines")

    print("\nScoring market...")
    result = score_market(test_market, filtered)
    print(f"\nConfidence: {result['confidence']:.2f}")
    print(f"Reasoning: {result['reasoning']}")
