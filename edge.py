from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import config
from markets import Market

if TYPE_CHECKING:
    # Only needed for type hints on the V2 (news-pipeline) path. Importing these
    # eagerly would drag in `anthropic`, which the market-data bot doesn't need.
    from classifier import Classification
    from news_stream import NewsEvent


@dataclass
class Signal:
    market: Market
    claude_score: float
    market_price: float
    edge: float
    side: str  # "YES" or "NO"
    bet_amount: float
    reasoning: str
    headlines: str
    # V2 fields
    news_source: str = ""
    classification: str = ""
    materiality: float = 0.0
    news_latency_ms: int = 0
    classification_latency_ms: int = 0
    total_latency_ms: int = 0


def detect_edge(
    market: Market,
    claude_score: float,
    reasoning: str = "",
    headlines: str = "",
) -> Signal | None:
    """V1: Compare Claude's confidence against market price."""
    market_price = market.yes_price
    edge = claude_score - market_price

    if abs(edge) < config.EDGE_THRESHOLD:
        return None

    if edge > 0:
        side = "YES"
        raw_edge = edge
    else:
        side = "NO"
        raw_edge = abs(edge)

    bet_amount = size_position(raw_edge)

    return Signal(
        market=market,
        claude_score=claude_score,
        market_price=market_price,
        edge=raw_edge,
        side=side,
        bet_amount=bet_amount,
        reasoning=reasoning,
        headlines=headlines,
    )


def detect_edge_v2(
    market: Market,
    classification: Classification,
    news_event: NewsEvent,
) -> Signal | None:
    """
    V2: Use classification direction + materiality instead of probability estimation.
    Only generates a signal when:
    - Direction is bullish or bearish (not neutral)
    - Materiality exceeds threshold
    - Market price has room to move in the predicted direction
    """
    if classification.direction == "neutral":
        return None

    if classification.materiality < config.MATERIALITY_THRESHOLD:
        return None

    market_price = market.yes_price

    if classification.direction == "bullish":
        side = "YES"
        # Don't buy YES on markets already priced high
        if market_price > 0.85:
            return None
        edge = classification.materiality * (1.0 - market_price)
    else:  # bearish
        side = "NO"
        # Don't buy NO on markets already priced low
        if market_price < 0.15:
            return None
        edge = classification.materiality * market_price

    if edge < config.EDGE_THRESHOLD:
        return None

    bet_amount = size_position(edge)
    total_latency = news_event.latency_ms + classification.latency_ms

    return Signal(
        market=market,
        claude_score=classification.materiality,
        market_price=market_price,
        edge=edge,
        side=side,
        bet_amount=bet_amount,
        reasoning=classification.reasoning,
        headlines=news_event.headline,
        news_source=news_event.source,
        classification=classification.direction,
        materiality=classification.materiality,
        news_latency_ms=news_event.latency_ms,
        classification_latency_ms=classification.latency_ms,
        total_latency_ms=total_latency,
    )


def size_position(edge: float) -> float:
    """Quarter-Kelly position sizing. Capped at MAX_BET_USD."""
    fraction = edge * 0.25
    bankroll = config.DAILY_LOSS_LIMIT_USD * 10
    raw_size = bankroll * fraction
    return min(max(round(raw_size, 2), 1.0), config.MAX_BET_USD)
