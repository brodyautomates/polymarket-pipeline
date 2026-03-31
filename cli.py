#!/usr/bin/env python3
"""
CLI interface for the Polymarket News Pipeline.

Usage:
    python cli.py run                  # Run full pipeline (dry-run by default)
    python cli.py run --live           # Run with live trading enabled
    python cli.py run --max 5          # Scan max 5 markets
    python cli.py run --hours 12       # Look back 12 hours for news
    python cli.py dashboard            # Launch live terminal dashboard (demo mode)
    python cli.py dashboard --speed 5  # Faster scan cycles (5s)
    python cli.py scrape               # Test scraper only
    python cli.py markets              # View available markets
    python cli.py trades               # View recent trade log
    python cli.py stats                # View trade statistics
"""

import argparse
import sys

from rich.console import Console
from rich.table import Table

console = Console()


def cmd_run(args):
    import config
    from pipeline import run_pipeline

    if args.live:
        config.DRY_RUN = False
        console.print("[red bold]LIVE TRADING ENABLED[/red bold]\n")
    else:
        console.print("[yellow]Dry-run mode (use --live to trade for real)[/yellow]\n")

    if args.threshold:
        config.EDGE_THRESHOLD = args.threshold

    run_pipeline(
        max_markets=args.max,
        lookback_hours=args.hours,
    )


def cmd_scrape(args):
    from scraper import scrape_all

    news = scrape_all(args.hours)
    console.print(f"\n[bold]Scraped {len(news)} headlines[/bold] (last {args.hours}h)\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Age", justify="right", width=6)
    table.add_column("Source", max_width=20)
    table.add_column("Headline", max_width=80)

    for item in news[:30]:
        table.add_row(f"{item.age_hours():.1f}h", item.source[:20], item.headline[:80])

    console.print(table)


def cmd_markets(args):
    from markets import fetch_active_markets, filter_by_categories

    all_markets = fetch_active_markets(limit=args.max)
    markets = filter_by_categories(all_markets)

    console.print(f"\n[bold]{len(markets)} markets in target categories[/bold] (of {len(all_markets)} fetched)\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Category", width=12)
    table.add_column("Question", max_width=60)
    table.add_column("YES", justify="right")
    table.add_column("NO", justify="right")
    table.add_column("Volume", justify="right")

    for m in markets:
        table.add_row(
            m.category,
            m.question[:60],
            f"{m.yes_price:.2f}",
            f"{m.no_price:.2f}",
            f"${m.volume:,.0f}",
        )

    console.print(table)


def cmd_trades(args):
    import logger

    trades = logger.get_recent_trades(limit=args.limit)
    if not trades:
        console.print("[yellow]No trades logged yet.[/yellow]")
        return

    console.print(f"\n[bold]Last {len(trades)} trades[/bold]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", justify="right")
    table.add_column("Market", max_width=45)
    table.add_column("Side")
    table.add_column("Claude", justify="right")
    table.add_column("Market$", justify="right")
    table.add_column("Edge", justify="right")
    table.add_column("Bet", justify="right")
    table.add_column("Status")
    table.add_column("Time", width=16)

    for t in trades:
        table.add_row(
            str(t["id"]),
            t["market_question"][:45],
            t["side"],
            f"{t['claude_score']:.2f}",
            f"{t['market_price']:.2f}",
            f"{t['edge']:.1%}",
            f"${t['amount_usd']:.2f}",
            t["status"],
            t["created_at"][:16],
        )

    console.print(table)


def cmd_dashboard(args):
    from dashboard import run_dashboard
    run_dashboard(scan_interval=args.speed)


def cmd_stats(args):
    import logger

    stats = logger.get_trade_stats()
    daily = logger.get_daily_pnl()

    console.print(f"\n[bold]Trade Statistics[/bold]\n")
    console.print(f"  Total trades: {stats['total_trades']}")
    console.print(f"  Daily exposure: ${abs(daily):.2f}")
    console.print(f"  By status:")
    for status, count in stats["by_status"].items():
        console.print(f"    {status}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Polymarket News Pipeline")
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Run the full pipeline")
    p_run.add_argument("--live", action="store_true", help="Enable live trading")
    p_run.add_argument("--max", type=int, default=10, help="Max markets to scan")
    p_run.add_argument("--hours", type=int, default=6, help="News lookback hours")
    p_run.add_argument("--threshold", type=float, default=None, help="Edge threshold override")
    p_run.set_defaults(func=cmd_run)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch live terminal dashboard")
    p_dash.add_argument("--speed", type=float, default=8.0, help="Seconds between scan cycles")
    p_dash.set_defaults(func=cmd_dashboard)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Test the news scraper")
    p_scrape.add_argument("--hours", type=int, default=6, help="Lookback hours")
    p_scrape.set_defaults(func=cmd_scrape)

    # markets
    p_markets = sub.add_parser("markets", help="View available markets")
    p_markets.add_argument("--max", type=int, default=50, help="Max markets to fetch")
    p_markets.set_defaults(func=cmd_markets)

    # trades
    p_trades = sub.add_parser("trades", help="View trade log")
    p_trades.add_argument("--limit", type=int, default=20, help="Number of trades to show")
    p_trades.set_defaults(func=cmd_trades)

    # stats
    p_stats = sub.add_parser("stats", help="View trade statistics")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
