"""
Backtest the market-data bot strategies against resolved Polymarket markets.

For each resolved market we know the true outcome and can pull its full
historical price series from the CLOB /prices-history endpoint. We replay each
strategy over that series: at the first point a strategy would have entered, we
record the entry side/price, then settle at resolution ($1 if the chosen side
won, $0 otherwise). Aggregated per strategy: trade count, win rate, total P&L,
and ROI on a fixed stake.

This is an honest first-entry-and-hold backtest. It ignores fees and assumes
fills at the shown price; treat the numbers as directional, not a guarantee.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from rich.console import Console
from rich.table import Table

import config

console = Console()
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"


@dataclass
class BTTrade:
    strategy: str
    question: str
    side: str
    entry: float
    won: bool
    pnl: float
    roi: float


def _fetch_resolved(limit: int, category: str | None) -> list[dict]:
    # Gamma caps each request at 100, so page through with an offset until we
    # have `limit` usable resolved markets (or the feed runs out).
    out: list[dict] = []
    offset = 0
    page_size = 100
    empty_pages = 0
    while len(out) < limit and empty_pages < 3:
        resp = httpx.get(
            f"{GAMMA_API}/markets",
            params={
                "limit": page_size, "offset": offset, "closed": True,
                "order": "volumeNum", "ascending": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        offset += page_size
        added = 0
        for m in page:
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except json.JSONDecodeError:
                    continue
            if not prices or len(prices) < 2 or str(prices[0]) not in ("0", "1"):
                continue
            toks = m.get("clobTokenIds")
            if isinstance(toks, str):
                try:
                    toks = json.loads(toks)
                except json.JSONDecodeError:
                    continue
            if not toks:
                continue
            q = m.get("question", "")
            if category and category.lower() not in q.lower():
                continue
            out.append({
                "question": q,
                "outcome_yes": str(prices[0]) == "1",
                "yes_token": toks[0],
            })
            added += 1
            if len(out) >= limit:
                break
        empty_pages = empty_pages + 1 if added == 0 else 0
    return out


def _fetch_history(token_id: str, client: httpx.Client) -> list[float]:
    try:
        r = client.get(
            f"{CLOB_HOST}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": "60"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    hist = data.get("history", data if isinstance(data, list) else [])
    return [float(pt["p"]) for pt in hist if "p" in pt]


# --- entry logic mirrors strategy.py, replayed over a historical series ---

def _entry_favorite_longshot(series: list[float]):
    lo, hi = config.FAV_LONGSHOT_BAND
    for p in series:
        if lo <= p <= hi:
            return "YES", p
        if lo <= (1 - p) <= hi:
            return "NO", 1 - p
    return None


def _entry_mean_reversion(series: list[float]):
    w = config.MEANREV_WINDOW
    for i in range(w, len(series)):
        avg = sum(series[i - w:i]) / w
        dev = series[i] - avg
        if abs(dev) < config.MEANREV_MIN_DEVIATION:
            continue
        return ("YES", series[i]) if dev < 0 else ("NO", 1 - series[i])
    return None


def _entry_momentum(series: list[float]):
    w = config.MOMENTUM_WINDOW
    for i in range(w, len(series)):
        window = series[i - w:i + 1]
        move = window[-1] - window[0]
        if abs(move) < config.MOMENTUM_MIN_MOVE:
            continue
        steps = [window[j + 1] - window[j] for j in range(len(window) - 1)]
        up = sum(1 for s in steps if s > 0)
        down = sum(1 for s in steps if s < 0)
        if move > 0 and up > down:
            return "YES", window[-1]
        if move < 0 and down > up:
            return "NO", 1 - window[-1]
    return None


ENTRY_FNS = {
    "favorite_longshot": _entry_favorite_longshot,
    "mean_reversion": _entry_mean_reversion,
    "momentum": _entry_momentum,
}


def run_backtest(limit: int = 40, category: str | None = None,
                 stake: float = 10.0, strategies: list[str] | None = None):
    strategies = strategies or ["favorite_longshot", "mean_reversion", "momentum"]
    strategies = [s for s in strategies if s in ENTRY_FNS]

    console.print(f"[bold]Fetching up to {limit} resolved markets...[/bold]")
    markets = _fetch_resolved(limit, category)
    console.print(f"  Got {len(markets)} resolved markets. Pulling price history...\n")

    trades: list[BTTrade] = []
    with httpx.Client(timeout=30) as client:
        for i, m in enumerate(markets):
            series = _fetch_history(m["yes_token"], client)
            if len(series) < config.MEANREV_WINDOW + 1:
                continue
            for strat in strategies:
                entry = ENTRY_FNS[strat](series)
                if not entry:
                    continue
                side, price = entry
                if price <= 0 or price >= 1:
                    continue
                won = m["outcome_yes"] if side == "YES" else (not m["outcome_yes"])
                shares = stake / price
                payout = shares if won else 0.0
                pnl = payout - stake
                trades.append(BTTrade(
                    strategy=strat, question=m["question"], side=side,
                    entry=price, won=won, pnl=pnl, roi=pnl / stake * 100,
                ))
            if (i + 1) % 10 == 0:
                console.print(f"  ...processed {i + 1}/{len(markets)} markets")

    _report(trades, stake, len(markets))
    return trades


def _report(trades: list[BTTrade], stake: float, n_markets: int):
    if not trades:
        console.print("[yellow]No qualifying trades in this sample.[/yellow]")
        return

    table = Table(title=f"Strategy Backtest — {n_markets} resolved markets, ${stake:.0f}/trade",
                  show_header=True, header_style="bold cyan")
    table.add_column("Strategy")
    table.add_column("Trades", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Total P&L", justify="right")
    table.add_column("ROI/trade", justify="right")

    by_strat: dict[str, list[BTTrade]] = {}
    for t in trades:
        by_strat.setdefault(t.strategy, []).append(t)

    for strat, ts in by_strat.items():
        wins = sum(1 for t in ts if t.won)
        total_pnl = sum(t.pnl for t in ts)
        avg_roi = sum(t.roi for t in ts) / len(ts)
        pnl_color = "bright_green" if total_pnl >= 0 else "red"
        table.add_row(
            strat, str(len(ts)), f"{wins / len(ts) * 100:.0f}%",
            f"[{pnl_color}]${total_pnl:+,.2f}[/{pnl_color}]", f"{avg_roi:+.1f}%",
        )

    total = sum(t.pnl for t in trades)
    invested = stake * len(trades)
    console.print(table)
    color = "bright_green" if total >= 0 else "red"
    console.print(
        f"\n  [bold]Overall:[/bold] {len(trades)} trades, "
        f"${invested:,.0f} deployed, "
        f"[{color}]${total:+,.2f} P&L ({total / invested * 100:+.1f}% ROI)[/{color}]"
    )
    console.print("  [dim]First-entry-and-hold; excludes fees/slippage. Directional only.[/dim]")
