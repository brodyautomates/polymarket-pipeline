from __future__ import annotations

from dataclasses import dataclass

import config
from markets import Market


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


def detect_edge(
    market: Market,
    claude_score: float,
    reasoning: str = "",
    headlines: str = "",
) -> Signal | None:
    """Compare Claude's confidence against market price. Return a Signal if edge exceeds threshold."""
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


def size_position(edge: float) -> float:
    """
    Simplified Kelly criterion for position sizing.
    Full Kelly = edge / odds, but we use quarter-Kelly for safety.
    Capped at MAX_BET_USD.
    """
    # Quarter-Kelly: conservative sizing
    fraction = (edge * 0.25)
    # Scale to a dollar amount (base bankroll = 10x daily limit)
    bankroll = config.DAILY_LOSS_LIMIT_USD * 10
    raw_size = bankroll * fraction

    return min(max(round(raw_size, 2), 1.0), config.MAX_BET_USD)
