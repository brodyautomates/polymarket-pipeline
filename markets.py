from __future__ import annotations

from dataclasses import dataclass

import httpx

import config

GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class Market:
    condition_id: str
    question: str
    category: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str
    active: bool
    tokens: list[dict]

    @property
    def implied_probability(self) -> float:
        return self.yes_price


def fetch_active_markets(limit: int = 50) -> list[Market]:
    """Fetch active, liquid markets from Polymarket's Gamma API."""
    markets = []

    try:
        resp = httpx.get(
            f"{GAMMA_API}/markets",
            params={
                "limit": limit,
                "active": True,
                "closed": False,
                "order": "volume",
                "ascending": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[markets] Gamma API error: {e}, falling back to CLOB...")
        return _fetch_from_clob(limit)

    items = data if isinstance(data, list) else data.get("data", [])

    for m in items:
        try:
            # Gamma API uses outcomePrices as a JSON string
            outcome_prices = m.get("outcomePrices", "")
            yes_price = 0.5
            no_price = 0.5

            if outcome_prices:
                import json
                try:
                    prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                    if len(prices) >= 2:
                        yes_price = float(prices[0])
                        no_price = float(prices[1])
                except (json.JSONDecodeError, ValueError):
                    pass

            # Also check tokens array
            tokens = m.get("tokens", m.get("clobTokenIds", []))
            if isinstance(tokens, str):
                import json
                try:
                    tokens = json.loads(tokens)
                except json.JSONDecodeError:
                    tokens = []

            # Build token list for order execution
            clob_token_ids = m.get("clobTokenIds", "")
            if isinstance(clob_token_ids, str):
                import json
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except json.JSONDecodeError:
                    clob_token_ids = []

            token_list = []
            outcomes = ["Yes", "No"]
            for i, tid in enumerate(clob_token_ids if isinstance(clob_token_ids, list) else []):
                token_list.append({
                    "token_id": tid,
                    "outcome": outcomes[i] if i < len(outcomes) else f"Outcome_{i}",
                    "price": yes_price if i == 0 else no_price,
                })

            vol = float(m.get("volume", m.get("volumeNum", 0)) or 0)
            question = m.get("question", "")

            # Skip resolved or low-info markets
            if yes_price in (0.0, 1.0) and vol == 0:
                continue

            markets.append(Market(
                condition_id=m.get("conditionId", m.get("condition_id", m.get("id", ""))),
                question=question,
                category=_infer_category(question, m.get("tags", None) or []),
                yes_price=yes_price,
                no_price=no_price,
                volume=vol,
                end_date=m.get("endDate", m.get("end_date_iso", "")),
                active=m.get("active", True),
                tokens=token_list,
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # Sort by volume descending
    markets.sort(key=lambda x: x.volume, reverse=True)
    return markets


def _fetch_from_clob(limit: int) -> list[Market]:
    """Fallback: fetch from CLOB API directly."""
    markets = []
    try:
        resp = httpx.get(
            f"{config.POLYMARKET_HOST}/markets",
            params={"limit": limit, "active": True},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[markets] CLOB API error: {e}")
        return markets

    items = data if isinstance(data, list) else data.get("data", data.get("markets", []))

    for m in items:
        try:
            tokens = m.get("tokens", [])
            yes_price = 0.5
            no_price = 0.5
            for t in tokens:
                outcome = t.get("outcome", "").lower()
                price = float(t.get("price", 0.5))
                if outcome == "yes":
                    yes_price = price
                elif outcome == "no":
                    no_price = price

            markets.append(Market(
                condition_id=m.get("condition_id", m.get("id", "")),
                question=m.get("question", ""),
                category=_infer_category(m.get("question", ""), m.get("tags") or []),
                yes_price=yes_price,
                no_price=no_price,
                volume=float(m.get("volume", 0)),
                end_date=m.get("end_date_iso", m.get("end_date", "")),
                active=m.get("active", True),
                tokens=tokens,
            ))
        except (KeyError, ValueError):
            continue

    return markets


def _infer_category(question: str, tags: list) -> str:
    """Infer category from question text and tags."""
    q = question.lower()
    tag_str = " ".join(str(t).lower() for t in tags)
    combined = f"{q} {tag_str}"

    if any(kw in combined for kw in ["ai", "artificial intelligence", "openai", "chatgpt", "llm", "google ai", "anthropic"]):
        return "ai"
    if any(kw in combined for kw in ["bitcoin", "ethereum", "crypto", "blockchain", "defi", "token"]):
        return "crypto"
    if any(kw in combined for kw in ["election", "president", "congress", "senate", "trump", "biden", "political"]):
        return "politics"
    if any(kw in combined for kw in ["spacex", "nasa", "climate", "research", "study", "discovery"]):
        return "science"
    if any(kw in combined for kw in ["tech", "apple", "google", "microsoft", "software", "startup"]):
        return "technology"
    return "other"


def filter_by_categories(markets: list[Market], categories: list[str] | None = None) -> list[Market]:
    """Filter markets to only target categories."""
    cats = categories or config.MARKET_CATEGORIES
    return [m for m in markets if m.category in cats]


def get_token_id(market: Market, side: str) -> str | None:
    """Get the token ID for a given side (YES/NO)."""
    for t in market.tokens:
        if t.get("outcome", "").upper() == side.upper():
            return t.get("token_id")
    return None


if __name__ == "__main__":
    all_markets = fetch_active_markets(limit=20)
    filtered = filter_by_categories(all_markets)
    print(f"\n--- {len(filtered)} markets in target categories (of {len(all_markets)} total) ---\n")
    for m in filtered[:15]:
        print(f"  [{m.category}] {m.question}")
        print(f"    YES: {m.yes_price:.2f} | NO: {m.no_price:.2f} | Vol: ${m.volume:,.0f}")
        print()
