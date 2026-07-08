"""
Market-data trading bot for Polymarket.

A self-contained trading loop that needs NO paid API keys. It:
  1. Fetches live markets from Polymarket's public Gamma API
  2. Runs the strategy engine (favorite-longshot bias, mean-reversion)
  3. Applies risk limits (per-position cap, total exposure cap, max positions)
  4. Executes trades — paper by default (portfolio.py ledger), or live via the
     CLOB client when run with --live and credentials are configured
  5. Marks the portfolio to market and manages exits (take-profit / stop-loss /
     resolution)

Run:
    python cli.py bot                    # one cycle, paper trading
    python cli.py bot --loop             # run continuously
    python cli.py bot --cycles 5         # five cycles
    python cli.py bot --live             # place real orders (careful!)
"""
from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
import portfolio
from markets import fetch_active_markets, Market
from strategy import generate_proposals, Proposal

console = Console()

# Exit rules for open positions, relative to entry price (marks against live
# mid-price in paper mode). A near-certain mark captures profit before resolution.
TAKE_PROFIT_DELTA = 0.08   # sell once mark rises this far above entry
STOP_LOSS_DELTA = 0.15     # sell once mark falls this far below entry
NEAR_CERTAIN = 0.985       # sell to capture value as a market nears resolution


def _fetch_markets() -> list[Market]:
    markets = fetch_active_markets(limit=200)
    # Keep only markets inside the configured volume window.
    return [
        m for m in markets
        if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD
    ]


def _price_lookup(markets: list[Market]) -> dict[str, float]:
    return {m.condition_id: m.yes_price for m in markets if m.condition_id}


def _size_position(proposal: Proposal, bankroll: float) -> float:
    """Confidence-weighted fraction of bankroll, capped by MAX_POSITION_PCT and MAX_BET_USD."""
    cap = min(bankroll * config.MAX_POSITION_PCT, config.MAX_BET_USD)
    usd = cap * proposal.confidence
    return round(max(usd, 0.0), 2)


def manage_exits(markets: list[Market], live: bool) -> int:
    """Close positions that hit take-profit, stop-loss, or resolved."""
    prices = _price_lookup(markets)
    active_ids = {m.condition_id for m in markets}
    closed = 0
    for pos in portfolio.get_open_positions():
        yes_price = prices.get(pos.market_id)
        if yes_price is None:
            # Market no longer in the active set → likely resolved. Settle at
            # the last known avg (conservative) unless we can infer the outcome.
            continue
        mark = yes_price if pos.side == "YES" else (1.0 - yes_price)
        reason = None
        if mark >= NEAR_CERTAIN or mark >= pos.avg_price + TAKE_PROFIT_DELTA:
            reason = "take_profit"
        elif mark <= pos.avg_price - STOP_LOSS_DELTA:
            reason = "stop_loss"
        if reason:
            pnl = portfolio.sell(pos, price=mark, note=reason)
            closed += 1
            color = "bright_green" if pnl >= 0 else "red"
            console.print(
                f"  [{color}]EXIT[/{color}] {reason} {pos.side} "
                f"\"{pos.question[:40]}\" @ {mark:.3f}  P&L ${pnl:+.2f}"
            )
    return closed


def run_cycle(live: bool = False) -> dict:
    markets = _fetch_markets()
    if not markets:
        console.print("[yellow]No markets in volume window this cycle.[/yellow]")
        return {"proposals": 0, "trades": 0, "exits": 0}

    # 1. Manage existing positions first.
    exits = manage_exits(markets, live)

    # 2. Generate new proposals.
    proposals = generate_proposals(markets)

    cash = portfolio.get_cash()
    summ = portfolio.summary(_price_lookup(markets))
    bankroll = summ["equity"]
    open_count = summ["open_positions"]
    exposure = summ["exposure"]
    max_exposure = bankroll * config.MAX_EXPOSURE_PCT

    trades = 0
    for prop in proposals:
        if open_count >= config.MAX_OPEN_POSITIONS:
            break
        # One position per market/side.
        if portfolio.find_open_position(prop.market.condition_id, prop.side):
            continue
        usd = _size_position(prop, bankroll)
        if usd < 1.0 or usd > cash:
            continue
        if exposure + usd > max_exposure:
            continue

        if live:
            result = _execute_live(prop, usd)
            if result.get("status") != "executed":
                console.print(f"  [red]live order failed:[/red] {result.get('status')}")
                continue

        pos = portfolio.buy(
            market_id=prop.market.condition_id,
            token_id=_token_id(prop),
            question=prop.market.question,
            side=prop.side,
            price=prop.price,
            usd=usd,
            strategy=prop.strategy,
        )
        if not pos:
            continue
        trades += 1
        open_count += 1
        exposure += usd
        cash -= usd
        console.print(
            f"  [bright_green]BUY[/bright_green] [{prop.strategy}] {prop.side} "
            f"${usd:.2f} @ {prop.price:.3f}  conf {prop.confidence:.2f}  "
            f"\"{prop.market.question[:45]}\""
        )

    _print_portfolio(markets)
    return {"proposals": len(proposals), "trades": trades, "exits": exits}


def _token_id(prop: Proposal) -> str | None:
    from markets import get_token_id
    return get_token_id(prop.market, prop.side)


def _execute_live(prop: Proposal, usd: float) -> dict:
    """Place a real CLOB order. Reuses the shared live-execution helper."""
    from edge import Signal
    from executor import execute_trade
    signal = Signal(
        market=prop.market,
        claude_score=prop.confidence,
        market_price=prop.market.yes_price,
        edge=prop.confidence,
        side=prop.side,
        bet_amount=usd,
        reasoning=prop.reasoning,
        headlines="",
        classification=prop.strategy,
        materiality=prop.confidence,
    )
    return execute_trade(signal)


def _print_portfolio(markets: list[Market]):
    summ = portfolio.summary(_price_lookup(markets))
    pnl_color = "bright_green" if summ["total_pnl"] >= 0 else "red"
    console.print(
        f"\n  [dim]Portfolio:[/dim] equity [bold]${summ['equity']:,.2f}[/bold]  "
        f"cash ${summ['cash']:,.2f}  "
        f"positions {summ['open_positions']}  "
        f"exposure ${summ['exposure']:,.2f}  "
        f"P&L [{pnl_color}]${summ['total_pnl']:+,.2f} ({summ['return_pct']:+.1f}%)[/{pnl_color}]  "
        f"[dim](realized ${summ['realized_pnl']:+,.2f} / unrealized ${summ['unrealized_pnl']:+,.2f})[/dim]\n"
    )


def run_bot(live: bool = False, cycles: int = 1, loop: bool = False,
            interval: float | None = None):
    interval = interval if interval is not None else config.BOT_LOOP_INTERVAL_SECONDS
    mode = "[red bold]LIVE[/red bold]" if live else "[yellow]PAPER[/yellow]"
    console.print(Panel(
        f"Market-Data Trading Bot  |  Mode: {mode}\n"
        f"Strategies: {', '.join(config.BOT_STRATEGIES)}  |  "
        f"Bankroll: ${portfolio.summary()['equity']:,.2f}",
        style="bright_cyan",
    ))

    if live and (not config.POLYMARKET_PRIVATE_KEY or config.DRY_RUN):
        console.print(
            "[yellow]--live requested but POLYMARKET_PRIVATE_KEY is unset or DRY_RUN=true; "
            "staying in paper mode.[/yellow]"
        )
        live = False

    n = 0
    try:
        while True:
            n += 1
            console.print(f"[dim]── cycle {n} ─────────────────────────────[/dim]")
            stats = run_cycle(live=live)
            console.print(
                f"[dim]  cycle {n}: {stats['proposals']} proposals, "
                f"{stats['trades']} new, {stats['exits']} exits[/dim]"
            )
            if not loop and n >= cycles:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[bright_cyan]Bot stopped.[/bright_cyan]")

    _final_report()


def _final_report():
    markets = _fetch_markets()
    summ = portfolio.summary(_price_lookup(markets))
    table = Table(title="Final Portfolio", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Starting bankroll", f"${summ['starting_cash']:,.2f}")
    table.add_row("Equity", f"${summ['equity']:,.2f}")
    table.add_row("Cash", f"${summ['cash']:,.2f}")
    table.add_row("Open positions", str(summ["open_positions"]))
    table.add_row("Realized P&L", f"${summ['realized_pnl']:+,.2f}")
    table.add_row("Unrealized P&L", f"${summ['unrealized_pnl']:+,.2f}")
    table.add_row("Total P&L", f"${summ['total_pnl']:+,.2f} ({summ['return_pct']:+.1f}%)")
    console.print(table)


if __name__ == "__main__":
    run_bot()
