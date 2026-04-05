#!/usr/bin/env python3
"""
Polymarket Pipeline — V1 (synchronous) and V2 (async event-driven).
V1: Scrape → Score → Edge → Trade (loop-based)
V2: News stream → Match → Classify → Edge → Trade (event-driven)
"""
from __future__ import annotations

import asyncio
import signal
import time
import logging

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import config
import logger
from scraper import scrape_all
from markets import fetch_active_markets, filter_by_categories
from scorer import score_market, filter_news_for_market
from edge import detect_edge, detect_edge_v2, Signal
from executor import execute_trade, execute_trade_async, exit_position_async
from news_stream import NewsAggregator, NewsEvent
from market_watcher import MarketWatcher
from matcher import match_news_to_markets
from classifier import classify_async

console = Console()
log = logging.getLogger(__name__)


# ============================================================
# V2: Event-Driven Pipeline
# ============================================================

class PipelineV2:
    """Async event-driven pipeline. Runs indefinitely."""

    def __init__(self):
        self.news_queue: asyncio.Queue = asyncio.Queue()
        self.signal_queue: asyncio.Queue = asyncio.Queue()
        self.news_aggregator = NewsAggregator(self.news_queue)
        self.market_watcher = MarketWatcher()
        self.running = False
        self.stats = {
            "news_processed": 0,
            "markets_matched": 0,
            "signals_found": 0,
            "trades_executed": 0,
        }

    async def run(self):
        """Start all pipeline components concurrently."""
        self.running = True
        self._tasks: list[asyncio.Task] = []

        mode = "[red bold]LIVE[/red bold]" if not config.DRY_RUN else "[yellow]DRY RUN[/yellow]"
        console.print(Panel(f"Pipeline V2 Starting  |  Mode: {mode}", style="bright_green"))
        console.print(f"  Niche filter: ${config.MIN_VOLUME_USD:,.0f} - ${config.MAX_VOLUME_USD:,.0f} volume")
        console.print(f"  Materiality threshold: {config.MATERIALITY_THRESHOLD}")
        console.print(f"  Speed target: {config.SPEED_TARGET_SECONDS}s")
        console.print(f"  Take-profit: {config.TAKE_PROFIT_MULTIPLIER}x  |  Stop-loss: {config.STOP_LOSS_PCT:.0%}")
        console.print()

        # Graceful shutdown on SIGINT/SIGTERM
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self._shutdown()))

        try:
            self._tasks = [
                asyncio.create_task(self.news_aggregator.run(), name="news"),
                asyncio.create_task(self.market_watcher.run(), name="markets"),
                asyncio.create_task(self._process_news(), name="processor"),
                asyncio.create_task(self._execute_signals(), name="executor"),
                asyncio.create_task(self._monitor_positions(), name="monitor"),
                asyncio.create_task(self._status_printer(), name="status"),
            ]
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False

    async def _shutdown(self):
        """Graceful shutdown — cancel all tasks and log final stats."""
        console.print(f"\n[bright_yellow]Shutting down pipeline...[/bright_yellow]")
        self.running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        console.print(f"[bright_green]Final stats: {self.stats}[/bright_green]")

    async def _process_news(self):
        """Process each news event: match → classify → detect edge."""
        while True:
            event: NewsEvent = await self.news_queue.get()
            self.stats["news_processed"] += 1

            # Log the news event
            logger.log_news_event(
                headline=event.headline,
                source=event.source,
                received_at=event.received_at.isoformat(),
                latency_ms=event.latency_ms,
            )

            console.print(
                f"  [dim]NEWS[/dim] [{event.source}] "
                f"\"{event.headline[:80]}\" "
                f"({event.latency_ms}ms)"
            )

            # Match to niche markets
            matched = match_news_to_markets(
                event.headline,
                self.market_watcher.tracked_markets,
            )

            if not matched:
                console.print(f"  [dim]  → no market match[/dim]")
                continue

            self.stats["markets_matched"] += len(matched)

            # Deduplicate — skip markets already traded recently
            recent_ids = logger.get_recent_market_ids(hours=6)
            before_dedup = len(matched)
            matched = [m for m in matched if m.condition_id not in recent_ids]
            skipped = before_dedup - len(matched)
            if skipped:
                console.print(f"  [dim]  → skipped {skipped} already-traded market(s)[/dim]")
            if not matched:
                continue

            console.print(
                f"  [cyan]MATCH[/cyan] {len(matched)} market(s): "
                + ", ".join(f"\"{m.question[:35]}\"" for m in matched[:3])
                + ("..." if len(matched) > 3 else "")
            )

            # Classify against each matched market
            for market in matched:
                try:
                    classification = await classify_async(
                        event.headline, market, event.source
                    )

                    console.print(
                        f"  [dim]  → classify: {classification.direction} "
                        f"mat:{classification.materiality:.2f} "
                        f"on \"{market.question[:40]}\" "
                        f"({classification.latency_ms}ms)[/dim]"
                    )

                    signal = detect_edge_v2(market, classification, event)
                    if signal:
                        self.stats["signals_found"] += 1
                        await self.signal_queue.put(signal)
                        console.print(
                            f"  [bright_green]SIGNAL[/bright_green] "
                            f"[{event.source}] {classification.direction.upper()} "
                            f"mat:{classification.materiality:.2f} "
                            f"→ {signal.side} ${signal.bet_amount} "
                            f"on \"{market.question[:40]}...\" "
                            f"(edge:{signal.edge:.1%} {signal.total_latency_ms}ms)"
                        )
                    else:
                        reason = "neutral" if classification.direction == "neutral" else f"low mat ({classification.materiality:.2f})" if classification.materiality < config.MATERIALITY_THRESHOLD else f"low edge"
                        console.print(f"  [dim]  → no signal: {reason}[/dim]")
                except Exception as e:
                    console.print(f"  [red]  → classify error: {type(e).__name__}: {e}[/red]")

    async def _execute_signals(self):
        """Execute trades from the signal queue."""
        while True:
            signal: Signal = await self.signal_queue.get()
            result = await execute_trade_async(signal)
            self.stats["trades_executed"] += 1

            status_color = "bright_green" if result["status"] in ("dry_run", "executed") else "red"
            console.print(
                f"  [{status_color}]{result['status']}[/{status_color}] "
                f"{result['side']} ${result['amount']:.2f} "
                f"on \"{result['market'][:40]}\" "
                f"(edge:{result['edge']:.1%} latency:{result.get('latency_ms', 0)}ms)"
            )

    async def _monitor_positions(self):
        """Monitor open positions and exit on take-profit or stop-loss."""
        while True:
            await asyncio.sleep(config.POSITION_CHECK_INTERVAL)

            if config.DRY_RUN:
                continue

            positions = logger.get_open_positions()
            if not positions:
                continue

            for pos in positions:
                try:
                    from executor import _get_clob_client

                    client = _get_clob_client()

                    # Find the token_id from trade history
                    trades = client.get_trades()
                    token_id = None
                    for t in trades:
                        if t.get("market") == pos["market_id"]:
                            token_id = t.get("asset_id")
                            break

                    if not token_id:
                        continue

                    # Get current midpoint price
                    mid = client.get_midpoint(token_id)
                    current_price = float(mid.get("mid", "0"))
                    if current_price <= 0:
                        continue

                    entry_price = pos["market_price"]
                    ratio = current_price / entry_price if entry_price > 0 else 0

                    # Skip impossible take-profit targets
                    max_ratio = 1.0 / entry_price if entry_price > 0 else 0
                    tp_possible = max_ratio >= config.TAKE_PROFIT_MULTIPLIER

                    if tp_possible and ratio >= config.TAKE_PROFIT_MULTIPLIER:
                        result = await exit_position_async(pos, "exit_profit")
                        console.print(
                            f"  [bright_green]EXIT PROFIT[/bright_green] "
                            f"{ratio:.1f}x on \"{pos['market_question'][:40]}\" "
                            f"(entry=${entry_price:.4f} exit=${current_price:.4f})"
                        )
                    elif ratio <= config.STOP_LOSS_PCT:
                        result = await exit_position_async(pos, "exit_loss")
                        console.print(
                            f"  [red]EXIT LOSS[/red] "
                            f"{ratio:.1f}x on \"{pos['market_question'][:40]}\" "
                            f"(entry=${entry_price:.4f} exit=${current_price:.4f})"
                        )

                except Exception as e:
                    log.warning(f"[monitor] Error checking position {pos['id']}: {e}")

    async def _status_printer(self):
        """Print periodic status updates."""
        while True:
            await asyncio.sleep(30)
            ns = self.news_aggregator.stats
            open_pos = len(logger.get_open_positions())
            ws = "ws:✓" if self.market_watcher._ws_connected else "ws:✗"
            console.print(
                f"\n  [dim]──── Status ────[/dim]"
                f"\n  [dim]  News: {self.stats['news_processed']} "
                f"(tw:{ns.get('twitter', 0)} tg:{ns.get('telegram', 0)} rss:{ns.get('rss', 0)}) "
                f"| Matched: {self.stats['markets_matched']} "
                f"| Signals: {self.stats['signals_found']} "
                f"| Trades: {self.stats['trades_executed']}"
                f"\n  Markets: {len(self.market_watcher.tracked_markets)} tracked "
                f"| Open positions: {open_pos} "
                f"| {ws}[/dim]\n"
            )


def run_pipeline_v2():
    """Entry point for V2 event-driven pipeline."""
    pipeline = PipelineV2()
    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        console.print(f"\n[bright_green]Pipeline stopped. {pipeline.stats}[/bright_green]")


# ============================================================
# V1: Synchronous Loop Pipeline (preserved for backward compat)
# ============================================================

def run_pipeline(
    max_markets: int = 10,
    lookback_hours: int | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    """V1: Run the full pipeline once. Returns list of trade results."""

    run_id = logger.log_run_start()
    results = []
    signals: list[Signal] = []

    mode = "[yellow]DRY RUN[/yellow]" if config.DRY_RUN else "[red bold]LIVE[/red bold]"
    console.print(Panel(f"Pipeline V1 Run #{run_id}  |  Mode: {mode}", style="cyan"))

    # Step 1: Scrape News
    console.print("\n[bold]1. Scraping news...[/bold]")
    news = scrape_all(lookback_hours)
    console.print(f"   Found {len(news)} unique headlines")

    if not news:
        console.print("[yellow]   No news found. Aborting run.[/yellow]")
        logger.log_run_end(run_id, 0, 0, 0, "no_news")
        return results

    # Step 2: Fetch Markets
    console.print("\n[bold]2. Fetching Polymarket markets...[/bold]")
    all_markets = fetch_active_markets(limit=100)
    markets = filter_by_categories(all_markets, categories)[:max_markets]
    console.print(f"   {len(markets)} markets in target categories (of {len(all_markets)} total)")

    if not markets:
        console.print("[yellow]   No markets found. Aborting run.[/yellow]")
        logger.log_run_end(run_id, 0, 0, 0, "no_markets")
        return results

    # Step 2.5: Deduplicate — skip markets already traded recently
    recent_ids = logger.get_recent_market_ids(hours=6)
    if recent_ids:
        before = len(markets)
        markets = [m for m in markets if m.condition_id not in recent_ids]
        skipped = before - len(markets)
        if skipped:
            console.print(f"   [dim]Skipped {skipped} markets already traded in the last hour[/dim]")

    # Step 3: Score Each Market
    console.print(f"\n[bold]3. Scoring {len(markets)} markets against news...[/bold]")

    for i, market in enumerate(markets):
        console.print(f"\n   [{i+1}/{len(markets)}] {market.question[:80]}")
        console.print(f"   Market price: YES={market.yes_price:.2f} NO={market.no_price:.2f}")

        relevant_news = filter_news_for_market(market, news)
        console.print(f"   Relevant headlines: {len(relevant_news)}")

        score_result = score_market(market, relevant_news)
        claude_score = score_result["confidence"]
        reasoning = score_result["reasoning"]
        console.print(f"   Claude score: {claude_score:.2f}  (market: {market.yes_price:.2f})")

        headlines_str = "\n".join(n.headline for n in relevant_news[:5])
        signal = detect_edge(market, claude_score, reasoning, headlines_str)

        if signal:
            edge_pct = signal.edge * 100
            console.print(f"   [green bold]SIGNAL: {signal.side} | Edge: {edge_pct:.1f}% | Size: ${signal.bet_amount}[/green bold]")
            signals.append(signal)
        else:
            edge = abs(claude_score - market.yes_price)
            console.print(f"   [dim]No edge (diff: {edge:.2f}, threshold: {config.EDGE_THRESHOLD})[/dim]")

        time.sleep(0.5)

    # Step 4: Execute Trades
    if signals:
        console.print(f"\n[bold]4. Executing {len(signals)} trades...[/bold]")
        for signal in signals:
            result = execute_trade(signal)
            results.append(result)
            status_color = "green" if result["status"] in ("dry_run", "executed") else "red"
            console.print(f"   [{status_color}]{result['status']}[/{status_color}] {result['market'][:60]} | {result['side']} ${result['amount']}")
    else:
        console.print("\n[bold]4. No signals — nothing to execute.[/bold]")

    # Step 5: Check exits on open positions
    if not config.DRY_RUN:
        check_exits()

    logger.log_run_end(run_id, len(markets), len(signals), len(results))
    _print_summary(results, len(markets), len(signals))
    return results


def check_exits():
    """Check open positions for take-profit / stop-loss exits (V1 sync)."""
    from executor import _get_clob_client, exit_position

    positions = logger.get_open_positions()
    if not positions:
        return

    console.print(f"\n[bold]5. Checking {len(positions)} open positions...[/bold]")

    try:
        client = _get_clob_client()
        trades = client.get_trades()
    except Exception as e:
        console.print(f"   [red]Error connecting to CLOB: {e}[/red]")
        return

    for pos in positions:
        try:
            token_id = None
            for t in trades:
                if t.get("market") == pos["market_id"]:
                    token_id = t.get("asset_id")
                    break

            if not token_id:
                continue

            mid = client.get_midpoint(token_id)
            current_price = float(mid.get("mid", "0"))
            if current_price <= 0:
                continue

            entry_price = pos["market_price"]
            ratio = current_price / entry_price if entry_price > 0 else 0

            max_ratio = 1.0 / entry_price if entry_price > 0 else 0
            tp_possible = max_ratio >= config.TAKE_PROFIT_MULTIPLIER

            if tp_possible and ratio >= config.TAKE_PROFIT_MULTIPLIER:
                result = exit_position(pos, "exit_profit")
                console.print(
                    f"   [bright_green]EXIT PROFIT[/bright_green] {ratio:.1f}x "
                    f"\"{pos['market_question'][:50]}\" "
                    f"(${entry_price:.4f}→${current_price:.4f})"
                )
            elif ratio <= config.STOP_LOSS_PCT:
                result = exit_position(pos, "exit_loss")
                console.print(
                    f"   [red]EXIT LOSS[/red] {ratio:.1f}x "
                    f"\"{pos['market_question'][:50]}\" "
                    f"(${entry_price:.4f}→${current_price:.4f})"
                )
            else:
                console.print(
                    f"   [dim]HOLD {ratio:.2f}x \"{pos['market_question'][:50]}\"[/dim]"
                )

        except Exception as e:
            log.warning(f"[check_exits] Error on position {pos['id']}: {e}")


def _print_summary(results: list[dict], markets_scanned: int, signals_found: int):
    table = Table(title="Pipeline Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Markets scanned", str(markets_scanned))
    table.add_row("Signals found", str(signals_found))
    table.add_row("Trades placed", str(len(results)))
    table.add_row("Mode", "DRY RUN" if config.DRY_RUN else "LIVE")
    console.print(table)


if __name__ == "__main__":
    run_pipeline()
