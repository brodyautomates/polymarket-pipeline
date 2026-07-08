"""
Strategy engine for the market-data trading bot.

Each strategy inspects live Polymarket markets and proposes trades. No LLM, no
news feeds, no paid API keys — just the order book, price, liquidity, and time
to resolution. Every strategy returns Proposals; the bot applies risk limits
and portfolio accounting on top.

Built-in strategies
-------------------
favorite_longshot
    Exploits the well-documented favorite-longshot bias: bettors systematically
    overpay for longshots and underpay for favorites. We buy the favorite side
    when it sits in a price band (default 0.85-0.97) on a liquid, tight-spread
    market that resolves within a bounded horizon. Edge = the historical
    tendency of such favorites to resolve true more often than their price implies.

mean_reversion
    Tracks each market's recent YES-price history (persisted across loops) and
    buys the side that is cheap relative to the short moving average when the
    deviation exceeds a threshold. A bet that transient moves revert.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config
from markets import Market

DB_PATH = Path(__file__).parent / "trades.db"


@dataclass
class Proposal:
    market: Market
    side: str          # YES / NO
    price: float       # entry price for that side
    confidence: float  # 0-1, drives position sizing
    strategy: str
    reasoning: str


def _price_history_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            yes_price REAL NOT NULL,
            ts TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_market ON price_history(market_id)")
    conn.commit()
    conn.close()


def record_prices(markets: list[Market]):
    """Persist current YES prices so mean-reversion has a rolling window."""
    _price_history_init()
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "INSERT INTO price_history (market_id, yes_price, ts) VALUES (?, ?, ?)",
        [(m.condition_id, m.mid_price, now) for m in markets if m.condition_id],
    )
    conn.commit()
    conn.close()


def _recent_prices(market_id: str, window: int) -> list[float]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT yes_price FROM price_history WHERE market_id=? ORDER BY id DESC LIMIT ?",
        (market_id, window),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def tradeable(market: Market) -> bool:
    """Shared liquidity / sanity filter before any strategy runs."""
    if not market.condition_id or not market.active:
        return False
    if market.spread and market.spread > config.MAX_SPREAD:
        return False
    if market.liquidity and market.liquidity < config.MIN_LIQUIDITY_USD:
        return False
    if not (0.02 < market.yes_price < 0.98):
        # near-certain markets have no room / no edge for these strategies
        return False
    return True


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

def favorite_longshot(market: Market) -> Proposal | None:
    lo, hi = config.FAV_LONGSHOT_BAND
    price = market.yes_price
    side, side_price = "YES", price
    # The favorite is whichever side is priced high; bet that side.
    if not (lo <= price <= hi) and not (lo <= (1 - price) <= hi):
        return None
    if 1 - price > price:  # NO is the favorite
        side, side_price = "NO", 1 - price
        if not (lo <= side_price <= hi):
            return None
    else:
        if not (lo <= side_price <= hi):
            return None

    hours = market.hours_to_resolution()
    if hours is not None and (hours < 0 or hours > config.FAV_MAX_HOURS_TO_RESOLUTION):
        return None

    # Confidence scales with how deep in the favorite band we are and liquidity.
    depth = (side_price - lo) / max(hi - lo, 1e-6)      # 0 at band bottom, 1 at top
    confidence = round(min(0.4 + 0.6 * depth, 1.0), 3)
    return Proposal(
        market=market,
        side=side,
        price=side_price,
        confidence=confidence,
        strategy="favorite_longshot",
        reasoning=(
            f"Favorite {side} @ {side_price:.3f} in band [{lo:.2f},{hi:.2f}]; "
            f"favorite-longshot bias implies underpricing"
            + (f"; {hours:.0f}h to resolution" if hours is not None else "")
        ),
    )


def mean_reversion(market: Market) -> Proposal | None:
    history = _recent_prices(market.condition_id, config.MEANREV_WINDOW)
    if len(history) < config.MEANREV_WINDOW:
        return None  # not enough samples yet
    avg = sum(history) / len(history)
    price = market.mid_price
    deviation = price - avg
    if abs(deviation) < config.MEANREV_MIN_DEVIATION:
        return None

    if deviation < 0:
        # YES got cheaper than its recent average → buy YES, expect reversion up
        side, side_price = "YES", market.yes_price
    else:
        # YES got richer → buy NO, expect reversion down
        side, side_price = "NO", market.no_price

    confidence = round(min(abs(deviation) / (2 * config.MEANREV_MIN_DEVIATION), 1.0), 3)
    return Proposal(
        market=market,
        side=side,
        price=side_price,
        confidence=confidence,
        strategy="mean_reversion",
        reasoning=(
            f"Price {price:.3f} deviates {deviation:+.3f} from {config.MEANREV_WINDOW}-sample "
            f"avg {avg:.3f}; buy {side} expecting reversion"
        ),
    )


def momentum(market: Market) -> Proposal | None:
    """
    Trend-following: the mirror of mean-reversion. When price has moved
    consistently in one direction over the recent window, buy the side it is
    moving toward, betting the move continues.
    """
    window = config.MOMENTUM_WINDOW
    history = _recent_prices(market.condition_id, window)
    if len(history) < window:
        return None
    # _recent_prices returns newest-first; reverse to chronological.
    series = list(reversed(history))
    move = series[-1] - series[0]
    if abs(move) < config.MOMENTUM_MIN_MOVE:
        return None
    # Require the move to be monotonic-ish (majority of steps same direction).
    steps = [series[i + 1] - series[i] for i in range(len(series) - 1)]
    up = sum(1 for s in steps if s > 0)
    down = sum(1 for s in steps if s < 0)
    if move > 0 and up <= down:
        return None
    if move < 0 and down <= up:
        return None

    if move > 0:
        side, side_price = "YES", market.yes_price
    else:
        side, side_price = "NO", market.no_price
    confidence = round(min(abs(move) / (2 * config.MOMENTUM_MIN_MOVE), 1.0), 3)
    return Proposal(
        market=market,
        side=side,
        price=side_price,
        confidence=confidence,
        strategy="momentum",
        reasoning=(
            f"Price moved {move:+.3f} over last {window} samples "
            f"({up} up / {down} down steps); buy {side} to follow the trend"
        ),
    )


def scan_arbitrage(markets: list[Market], limit: int = 40) -> list[Proposal]:
    """
    Cross-side arbitrage: when best_ask(YES) + best_ask(NO) < 1, buying both
    guarantees a $1 payout for less than $1. Requires live order books, so this
    is a separate (networked) scan capped at the `limit` most liquid markets.
    Emits two legs (YES and NO) per opportunity.
    """
    import httpx
    from orderbook import check_arbitrage
    from markets import get_token_id

    candidates = sorted(
        [m for m in markets if m.condition_id and m.active],
        key=lambda m: m.liquidity, reverse=True,
    )[:limit]

    proposals: list[Proposal] = []
    with httpx.Client(timeout=15) as client:
        for m in candidates:
            yes_tok = get_token_id(m, "YES")
            no_tok = get_token_id(m, "NO")
            if not yes_tok or not no_tok:
                continue
            arb = check_arbitrage(yes_tok, no_tok, client)
            if not arb or arb["profit_per_pair"] < config.ARB_MIN_PROFIT:
                continue
            reasoning = (
                f"YES ask {arb['yes_ask']:.3f} + NO ask {arb['no_ask']:.3f} = "
                f"{arb['cost']:.3f} < 1.00 → risk-free {arb['return_pct']:.1f}%"
            )
            for side, price in (("YES", arb["yes_ask"]), ("NO", arb["no_ask"])):
                proposals.append(Proposal(
                    market=m, side=side, price=price, confidence=1.0,
                    strategy="arbitrage", reasoning=reasoning,
                ))
    return proposals


STRATEGIES = {
    "favorite_longshot": favorite_longshot,
    "mean_reversion": mean_reversion,
    "momentum": momentum,
}


def generate_proposals(markets: list[Market], enabled: list[str] | None = None) -> list[Proposal]:
    """Run all enabled strategies over the tradeable markets."""
    enabled = enabled or config.BOT_STRATEGIES
    record_prices(markets)  # keep the rolling window fresh for reversion/momentum
    proposals: list[Proposal] = []
    for market in markets:
        if not tradeable(market):
            continue
        for name in enabled:
            fn = STRATEGIES.get(name)
            if not fn:
                continue
            prop = fn(market)
            if prop:
                proposals.append(prop)
    # Arbitrage is a networked, order-book scan handled separately.
    if "arbitrage" in enabled:
        proposals.extend(scan_arbitrage(markets, limit=config.ARB_SCAN_LIMIT))
    # Best-conviction first.
    proposals.sort(key=lambda p: p.confidence, reverse=True)
    return proposals
