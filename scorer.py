from __future__ import annotations

import json

import anthropic

import config
from scraper import NewsItem
from markets import Market


client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SCORING_PROMPT = """You are a prediction market analyst. Your job is to estimate the probability that a specific market question will resolve YES, based on recent news headlines.

## Market Question
{question}

## Current Market Price
YES token price: {yes_price:.2f} (market's implied probability: {yes_price:.0%})

## Recent News Headlines (last {lookback}h)
{headlines}

## Instructions
1. Analyze each headline for relevance to the market question.
2. Consider base rates, recency of news, and source credibility.
3. Form an independent probability estimate — do NOT anchor to the current market price.
4. Be calibrated: 0.50 means you have no information, 0.90+ means near certainty.

Respond with ONLY valid JSON in this exact format:
{{
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<2-3 sentence explanation>",
  "relevant_headlines": [<indices of relevant headlines, 0-indexed>]
}}"""


def score_market(market: Market, news: list[NewsItem]) -> dict:
    """Score a market question against recent news using Claude."""
    headlines_text = "\n".join(
        f"[{i}] [{item.source}] ({item.age_hours():.1f}h ago) {item.headline}"
        for i, item in enumerate(news)
    )

    if not headlines_text.strip():
        return {
            "confidence": 0.5,
            "reasoning": "No relevant news found — returning baseline.",
            "relevant_headlines": [],
        }

    prompt = SCORING_PROMPT.format(
        question=market.question,
        yes_price=market.yes_price,
        lookback=config.NEWS_LOOKBACK_HOURS,
        headlines=headlines_text,
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
            "confidence": 0.5,
            "reasoning": f"Parsing error: {e}",
            "relevant_headlines": [],
        }
    except Exception as e:
        return {
            "confidence": 0.5,
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
