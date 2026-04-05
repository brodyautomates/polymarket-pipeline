"""
News-to-market matching — routes breaking news to relevant active markets.
Two strategies: fast keyword matching + semantic Claude matching for ambiguous cases.
"""
from __future__ import annotations

import logging
from markets import Market

log = logging.getLogger(__name__)


def extract_keywords(question: str) -> list[str]:
    """Extract meaningful keywords from a market question."""
    stopwords = {
        "will", "the", "a", "an", "be", "by", "in", "on", "at", "to",
        "of", "for", "is", "it", "this", "that", "and", "or", "not",
        "before", "after", "end", "yes", "no", "any", "has", "have",
        "does", "do", "than", "more", "less", "over", "under", "above",
        "below", "through", "during", "between", "reach", "exceed",
    }
    words = question.lower().split()
    keywords = [
        w.strip("?.,!\"'()[]")
        for w in words
        if w.strip("?.,!\"'()[]") not in stopwords and len(w.strip("?.,!\"'()[]")) > 2
    ]
    return keywords


def match_news_to_markets(
    headline: str,
    markets: list[Market],
    max_matches: int = 5,
) -> list[Market]:
    """
    Find markets that a news headline is relevant to.
    Uses keyword overlap scoring — fast, no API call.
    """
    headline_lower = headline.lower()
    scored = []

    for market in markets:
        keywords = extract_keywords(market.question)
        if not keywords:
            continue

        # Count keyword hits
        hits = sum(1 for kw in keywords if kw in headline_lower)
        if hits == 0:
            continue

        # Score = hits / total keywords (relevance ratio)
        score = hits / len(keywords)
        scored.append((score, market))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_matches]]


def match_news_to_markets_broad(
    headline: str,
    summary: str,
    markets: list[Market],
    max_matches: int = 5,
) -> list[Market]:
    """
    Broader matching using headline + summary text.
    Falls back to category matching if keyword matching returns nothing.
    """
    # Try keyword matching first
    matches = match_news_to_markets(headline, markets, max_matches)
    if matches:
        return matches

    # Fallback: match on category keywords in the headline
    combined = f"{headline} {summary}".lower()
    # Reuse the same category rules from markets.py for consistency
    from markets import _CATEGORY_RULES
    category_keywords = {cat: kws for cat, kws in _CATEGORY_RULES}

    matched_categories = set()
    for cat, kws in category_keywords.items():
        if any(kw in combined for kw in kws):
            matched_categories.add(cat)

    if not matched_categories:
        return []

    # Return markets in matching categories
    category_matches = [m for m in markets if m.category in matched_categories]
    return category_matches[:max_matches]


if __name__ == "__main__":
    from markets import fetch_active_markets, filter_by_categories
    import config

    print("Fetching markets...")
    all_m = fetch_active_markets(limit=100)
    filtered = filter_by_categories(all_m)
    niche = [m for m in filtered if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD]
    print(f"Niche markets: {len(niche)}")

    test_headlines = [
        "OpenAI reportedly testing GPT-5 internally with select partners",
        "Bitcoin ETF inflows hit $2.1B in single week",
        "Fed minutes signal growing consensus for summer rate cut",
    ]

    for h in test_headlines:
        matches = match_news_to_markets(h, niche)
        print(f"\n\"{h[:60]}...\"")
        print(f"  Matched {len(matches)} markets:")
        for m in matches:
            print(f"    [{m.category}] {m.question[:50]}")
