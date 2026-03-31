#!/usr/bin/env python3
"""
Polymarket News Pipeline
Scrape news → Score confidence → Detect edge → Execute trades
"""
from __future__ import annotations

import sys
import time

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import config
import logger
from scraper import scrape_all
from markets import fetch_active_markets, filter_by_categories
from scorer import score_market, filter_news_for_market
from edge import detect_edge, Signal
from executor import execute_trade

console = Console()


def run_pipeline(
    max_markets: int = 10,
    lookback_hours: int | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    """Run the full pipeline once. Returns list of trade results."""

    run_id = logger.log_run_start()
    results = []
    signals: list[Signal] = []

    mode = "[yellow]DRY RUN[/yellow]" if config.DRY_RUN else "[red bold]LIVE[/red bold]"
    console.print(Panel(f"Pipeline Run #{run_id}  |  Mode: {mode}", style="cyan"))

    # --- Step 1: Scrape News ---
    console.print("\n[bold]1. Scraping news...[/bold]")
    news = scrape_all(lookback_hours)
    console.print(f"   Found {len(news)} unique headlines")

    if not news:
        console.print("[yellow]   No news found. Aborting run.[/yellow]")
        logger.log_run_end(run_id, 0, 0, 0, "no_news")
        return results

    # --- Step 2: Fetch Markets ---
    console.print("\n[bold]2. Fetching Polymarket markets...[/bold]")
    all_markets = fetch_active_markets(limit=100)
    markets = filter_by_categories(all_markets, categories)[:max_markets]
    console.print(f"   {len(markets)} markets in target categories (of {len(all_markets)} total)")

    if not markets:
        console.print("[yellow]   No markets found. Aborting run.[/yellow]")
        logger.log_run_end(run_id, 0, 0, 0, "no_markets")
        return results

    # --- Step 3: Score Each Market ---
    console.print(f"\n[bold]3. Scoring {len(markets)} markets against news...[/bold]")

    for i, market in enumerate(markets):
        console.print(f"\n   [{i+1}/{len(markets)}] {market.question[:80]}")
        console.print(f"   Market price: YES={market.yes_price:.2f} NO={market.no_price:.2f}")

        # Filter relevant news
        relevant_news = filter_news_for_market(market, news)
        console.print(f"   Relevant headlines: {len(relevant_news)}")

        # Score with Claude
        score_result = score_market(market, relevant_news)
        claude_score = score_result["confidence"]
        reasoning = score_result["reasoning"]
        console.print(f"   Claude score: {claude_score:.2f}  (market: {market.yes_price:.2f})")

        # Check for edge
        headlines_str = "\n".join(n.headline for n in relevant_news[:5])
        signal = detect_edge(market, claude_score, reasoning, headlines_str)

        if signal:
            edge_pct = signal.edge * 100
            console.print(f"   [green bold]SIGNAL: {signal.side} | Edge: {edge_pct:.1f}% | Size: ${signal.bet_amount}[/green bold]")
            signals.append(signal)
        else:
            edge = abs(claude_score - market.yes_price)
            console.print(f"   [dim]No edge (diff: {edge:.2f}, threshold: {config.EDGE_THRESHOLD})[/dim]")

        time.sleep(0.5)  # rate limit courtesy

    # --- Step 4: Execute Trades ---
    if signals:
        console.print(f"\n[bold]4. Executing {len(signals)} trades...[/bold]")
        for signal in signals:
            result = execute_trade(signal)
            results.append(result)
            status_color = "green" if result["status"] in ("dry_run", "executed") else "red"
            console.print(f"   [{status_color}]{result['status']}[/{status_color}] {result['market'][:60]} | {result['side']} ${result['amount']}")
    else:
        console.print("\n[bold]4. No signals — nothing to execute.[/bold]")

    # --- Summary ---
    logger.log_run_end(run_id, len(markets), len(signals), len(results))
    _print_summary(results, len(markets), len(signals))

    return results


def _print_summary(results: list[dict], markets_scanned: int, signals_found: int):
    """Print a summary table of the pipeline run."""
    console.print("\n")
    table = Table(title="Pipeline Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Markets scanned", str(markets_scanned))
    table.add_row("Signals found", str(signals_found))
    table.add_row("Trades placed", str(len(results)))
    table.add_row("Mode", "DRY RUN" if config.DRY_RUN else "LIVE")
    console.print(table)

    if results:
        console.print()
        trades_table = Table(title="Trades", show_header=True, header_style="bold green")
        trades_table.add_column("Market", max_width=50)
        trades_table.add_column("Side")
        trades_table.add_column("Amount", justify="right")
        trades_table.add_column("Edge", justify="right")
        trades_table.add_column("Status")
        for r in results:
            trades_table.add_row(
                r["market"][:50],
                r["side"],
                f"${r['amount']:.2f}",
                f"{r['edge']:.1%}",
                r["status"],
            )
        console.print(trades_table)


if __name__ == "__main__":
    run_pipeline()
