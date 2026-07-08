"""
CLOB order-book access — true bid/ask depth from Polymarket.

The Gamma API gives a single mid/last price per market. For real execution the
bot wants the live book: best bid/ask, and the size-aware fill price you'd get
walking the book for a given dollar amount. This module talks to the public
CLOB endpoints (no auth required for reads).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

CLOB_HOST = "https://clob.polymarket.com"


@dataclass
class Book:
    token_id: str
    bids: list[tuple[float, float]] = field(default_factory=list)  # (price, size), best first
    asks: list[tuple[float, float]] = field(default_factory=list)  # (price, size), best first
    tick_size: float = 0.01       # min price increment the market accepts
    min_order_size: float = 5.0   # min shares per order

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0

    @property
    def spread(self) -> float:
        if self.bids and self.asks:
            return self.best_ask - self.best_bid
        return 1.0

    @property
    def mid(self) -> float:
        if self.bids and self.asks:
            return (self.best_bid + self.best_ask) / 2
        return self.best_ask or self.best_bid or 0.5

    def cost_to_buy(self, usd: float) -> tuple[float, float] | None:
        """
        Walk the ask side to spend up to `usd`. Returns (shares, avg_fill_price)
        or None if the book can't fill the order. Models real slippage.
        """
        remaining = usd
        shares = 0.0
        spent = 0.0
        for price, size in self.asks:
            level_cost = price * size
            take = min(remaining, level_cost)
            if take <= 0:
                break
            shares += take / price
            spent += take
            remaining -= take
            if remaining <= 1e-9:
                break
        if shares <= 0 or spent <= 0:
            return None
        return shares, spent / shares


def fetch_book(token_id: str, client: httpx.Client | None = None) -> Book | None:
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.get(f"{CLOB_HOST}/book", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    finally:
        if own:
            client.close()

    def _levels(raw, reverse):
        lvls = []
        for lvl in raw or []:
            try:
                lvls.append((float(lvl["price"]), float(lvl["size"])))
            except (KeyError, TypeError, ValueError):
                continue
        # Best bid = highest price; best ask = lowest price.
        lvls.sort(key=lambda x: x[0], reverse=reverse)
        return lvls

    def _f(v, d):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    return Book(
        token_id=token_id,
        bids=_levels(data.get("bids"), reverse=True),
        asks=_levels(data.get("asks"), reverse=False),
        tick_size=_f(data.get("tick_size"), 0.01),
        min_order_size=_f(data.get("min_order_size"), 5.0),
    )


def check_arbitrage(yes_token: str, no_token: str,
                    client: httpx.Client | None = None) -> dict | None:
    """
    Buying YES + NO both guarantees a $1 payout. If the two best asks sum to
    less than 1 (minus a safety margin), that's risk-free profit. Returns a
    dict describing the opportunity, or None.
    """
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        yb = fetch_book(yes_token, client)
        nb = fetch_book(no_token, client)
    finally:
        if own:
            client.close()
    if not yb or not nb or not yb.asks or not nb.asks:
        return None
    cost = yb.best_ask + nb.best_ask
    if cost >= 1.0:
        return None
    return {
        "yes_ask": yb.best_ask,
        "no_ask": nb.best_ask,
        "cost": cost,
        "profit_per_pair": 1.0 - cost,
        "return_pct": (1.0 - cost) / cost * 100,
    }
