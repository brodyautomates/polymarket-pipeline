#!/usr/bin/env python3
"""
Polymarket Pipeline — CLI Interface

Usage:
    python cli.py bot                  # Market-data trading bot (no paid API keys, paper by default)
    python cli.py bot --loop           # Run the bot continuously
    python cli.py bot --live           # Bot with live trading
    python cli.py portfolio            # Show the bot's paper-trading portfolio
    python cli.py verify-live          # Pre-flight check for live trading (no orders placed)
    python cli.py watch                # V2: Event-driven pipeline (real-time news → classify → trade)
    python cli.py watch --live         # V2: With live trading
    python cli.py run                  # V1: Synchronous pipeline (RSS → score → trade)
    python cli.py run --live           # V1: With live trading
    python cli.py dashboard            # Launch live terminal dashboard
    python cli.py backtest             # Backtest V2 strategy against resolved markets
    python cli.py calibrate            # Show classification accuracy report
    python cli.py niche                # Browse niche markets (< $500K volume)
    python cli.py verify               # Check all API keys and connections
    python cli.py scrape               # Test news scraper only
    python cli.py markets              # Browse all active markets
    python cli.py trades               # View trade log
    python cli.py stats                # Performance statistics
"""

import argparse
import sys

from rich.console import Console
from rich.table import Table

console = Console()


def cmd_watch(args):
    """V2: Event-driven pipeline — real-time news → classify → trade."""
    import config
    from pipeline import run_pipeline_v2

    if args.live:
        config.DRY_RUN = False
        console.print("[red bold]LIVE TRADING ENABLED[/red bold]\n")
    else:
        console.print("[yellow]Dry-run mode (use --live to trade for real)[/yellow]\n")

    if args.threshold:
        config.MATERIALITY_THRESHOLD = args.threshold

    run_pipeline_v2()


def cmd_run(args):
    """V1: Synchronous pipeline — RSS → score → trade."""
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


def cmd_bot(args):
    """Market-data trading bot — self-contained, no paid API keys needed."""
    import config
    from bot import run_bot

    if args.bankroll:
        import portfolio
        portfolio.reset(bankroll=args.bankroll)
        console.print(f"[cyan]Portfolio reset to ${args.bankroll:,.2f} bankroll[/cyan]")
    if args.strategies:
        config.BOT_STRATEGIES = [s.strip() for s in args.strategies.split(",") if s.strip()]

    run_bot(
        live=args.live,
        cycles=args.cycles,
        loop=args.loop,
        interval=args.interval,
    )


def cmd_portfolio(args):
    """Show the bot's paper-trading portfolio and open positions."""
    import portfolio
    from markets import fetch_active_markets
    from rich.panel import Panel

    if args.reset is not None:
        portfolio.reset(bankroll=args.reset if args.reset > 0 else None)
        console.print(f"[cyan]Portfolio reset.[/cyan]")
        return

    markets = fetch_active_markets(limit=200)
    prices = {m.condition_id: m.yes_price for m in markets if m.condition_id}
    summ = portfolio.summary(prices)

    pnl_color = "bright_green" if summ["total_pnl"] >= 0 else "red"
    console.print(Panel(
        f"[bold]Equity:[/bold] ${summ['equity']:,.2f}   "
        f"[bold]Cash:[/bold] ${summ['cash']:,.2f}   "
        f"[bold]P&L:[/bold] [{pnl_color}]${summ['total_pnl']:+,.2f} ({summ['return_pct']:+.1f}%)[/{pnl_color}]",
        title="Bot Portfolio", style="bright_cyan",
    ))

    positions = portfolio.get_open_positions()
    if not positions:
        console.print("[dim]No open positions.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Market", max_width=42)
    table.add_column("Side", width=4)
    table.add_column("Shares", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Mark", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Unreal. P&L", justify="right")
    table.add_column("Strategy", width=16)

    for p in positions:
        yes = prices.get(p.market_id)
        mark = (yes if p.side == "YES" else 1 - yes) if yes is not None else p.avg_price
        upnl = p.unrealized_pnl(mark)
        c = "bright_green" if upnl >= 0 else "red"
        table.add_row(
            p.question[:42], p.side, f"{p.shares:.1f}", f"{p.avg_price:.3f}",
            f"{mark:.3f}", f"${p.cost_basis:.2f}",
            f"[{c}]${upnl:+.2f}[/{c}]", p.strategy or "—",
        )
    console.print(table)


def cmd_backtest(args):
    """Run backtest against resolved markets."""
    from backtest import run_backtest
    run_backtest(limit=args.limit, category=args.category)


def cmd_botbacktest(args):
    """Backtest the market-data bot strategies over real historical prices."""
    from strategy_backtest import run_backtest as run_bot_backtest
    strategies = [s.strip() for s in args.strategies.split(",")] if args.strategies else None
    run_bot_backtest(
        limit=args.limit,
        category=args.category,
        stake=args.stake,
        strategies=strategies,
    )


def cmd_calibrate(args):
    """Show classification accuracy report."""
    from calibrator import check_resolutions, get_report
    from rich.panel import Panel

    console.print("[bold]Checking for resolved markets...[/bold]")
    resolved = check_resolutions()
    if resolved:
        console.print(f"  Updated {resolved} trade resolutions")

    report = get_report()

    console.print(Panel(f"[bold]CALIBRATION REPORT[/bold]", style="bright_cyan"))
    console.print(f"  Total resolved: {report.total}")
    console.print(f"  Accuracy: {report.accuracy:.1f}%")

    if report.by_source:
        console.print(f"\n  [bold]By Source:[/bold]")
        for source, acc in report.by_source.items():
            color = "bright_green" if acc >= 55 else ("yellow" if acc >= 45 else "red")
            console.print(f"    {source}: [{color}]{acc:.1f}%[/{color}]")

    if report.by_classification:
        console.print(f"\n  [bold]By Classification:[/bold]")
        for cls, acc in report.by_classification.items():
            color = "bright_green" if acc >= 55 else ("yellow" if acc >= 45 else "red")
            console.print(f"    {cls}: [{color}]{acc:.1f}%[/{color}]")

    console.print(f"\n  [dim]{report.recommendation}[/dim]")


def cmd_niche(args):
    """Browse niche markets only (volume-filtered)."""
    import config
    from markets import fetch_active_markets, filter_by_categories

    all_markets = fetch_active_markets(limit=200)
    categorized = filter_by_categories(all_markets)
    niche = [
        m for m in categorized
        if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD
    ]

    console.print(f"\n[bold]{len(niche)} niche markets[/bold] (${config.MIN_VOLUME_USD:,.0f} - ${config.MAX_VOLUME_USD:,.0f} volume)\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Category", width=12)
    table.add_column("Question", max_width=50)
    table.add_column("YES", justify="right")
    table.add_column("NO", justify="right")
    table.add_column("Volume", justify="right")

    for m in niche[:30]:
        table.add_row(
            m.category,
            m.question[:50],
            f"{m.yes_price:.2f}",
            f"{m.no_price:.2f}",
            f"${m.volume:,.0f}",
        )

    console.print(table)


def cmd_dashboard(args):
    from dashboard import run_dashboard
    run_dashboard(scan_interval=args.speed)


def cmd_verify(args):
    """Check all API keys and connections work."""
    from rich.panel import Panel

    console.print(Panel("[bold]POLYMARKET PIPELINE V2 — VERIFICATION[/bold]", style="bright_green"))
    all_good = True

    # 1. Python version
    v = sys.version_info
    py_ok = v.major == 3 and v.minor >= 9
    status = "[bright_green]PASS[/bright_green]" if py_ok else "[red]FAIL[/red]"
    console.print(f"  {status}  Python {v.major}.{v.minor}.{v.micro}")
    if not py_ok:
        all_good = False

    # 2. Dependencies
    deps_ok = True
    for mod in ["anthropic", "feedparser", "httpx", "rich", "dotenv", "websockets", "tweepy", "aiohttp"]:
        try:
            __import__(mod)
        except ImportError:
            console.print(f"  [red]FAIL[/red]  Missing module: {mod}")
            deps_ok = False
            all_good = False
    if deps_ok:
        console.print(f"  [bright_green]PASS[/bright_green]  All dependencies installed")

    # 3. .env exists
    import os
    env_exists = os.path.exists(os.path.join(os.path.dirname(__file__), ".env"))
    status = "[bright_green]PASS[/bright_green]" if env_exists else "[red]FAIL[/red] — run: cp .env.example .env"
    console.print(f"  {status}  .env file")
    if not env_exists:
        all_good = False

    # 4. Anthropic API key
    import config
    has_key = bool(config.ANTHROPIC_API_KEY) and config.ANTHROPIC_API_KEY != "sk-ant-..."
    if has_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say OK"}],
            )
            console.print(f"  [bright_green]PASS[/bright_green]  Anthropic API key (verified)")
        except Exception as e:
            console.print(f"  [red]FAIL[/red]  Anthropic API key — {type(e).__name__}: {e}")
            all_good = False
    else:
        console.print(f"  [red]FAIL[/red]  Anthropic API key not set")
        all_good = False

    # 5. News scraper (RSS)
    try:
        from scraper import scrape_rss
        items = scrape_rss(config.RSS_FEEDS[0], 12)
        console.print(f"  [bright_green]PASS[/bright_green]  RSS scraper ({len(items)} headlines)")
    except Exception as e:
        console.print(f"  [yellow]WARN[/yellow]  RSS scraper — {e}")

    # 6. Twitter API (optional)
    has_twitter = bool(config.TWITTER_BEARER_TOKEN)
    if has_twitter:
        console.print(f"  [bright_green]PASS[/bright_green]  Twitter bearer token set")
    else:
        console.print(f"  [dim]SKIP[/dim]  Twitter API (optional — enables real-time news stream)")

    # 7. Telegram (optional)
    has_telegram = bool(config.TELEGRAM_BOT_TOKEN)
    if has_telegram:
        console.print(f"  [bright_green]PASS[/bright_green]  Telegram bot token set")
    else:
        console.print(f"  [dim]SKIP[/dim]  Telegram bot (optional — enables channel monitoring)")

    # 8. Polymarket API
    try:
        from markets import fetch_active_markets
        mkts = fetch_active_markets(limit=5)
        console.print(f"  [bright_green]PASS[/bright_green]  Polymarket API ({len(mkts)} markets)")
    except Exception as e:
        console.print(f"  [yellow]WARN[/yellow]  Polymarket API — {e}")

    # 9. Niche market filter
    try:
        from markets import fetch_active_markets, filter_by_categories
        all_m = fetch_active_markets(limit=100)
        cat = filter_by_categories(all_m)
        niche = [m for m in cat if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD]
        console.print(f"  [bright_green]PASS[/bright_green]  Niche filter ({len(niche)} markets in range)")
    except Exception as e:
        console.print(f"  [yellow]WARN[/yellow]  Niche filter — {e}")

    # 10. Polymarket trading credentials (optional)
    has_poly = bool(config.POLYMARKET_API_KEY)
    if has_poly:
        console.print(f"  [bright_green]PASS[/bright_green]  Polymarket trading credentials set")
    else:
        console.print(f"  [dim]SKIP[/dim]  Polymarket trading credentials (optional — needed for --live)")

    # 11. SQLite
    try:
        import logger as _
        console.print(f"  [bright_green]PASS[/bright_green]  SQLite database (V2 schema)")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  SQLite — {e}")
        all_good = False

    # Summary
    console.print()
    if all_good:
        console.print(Panel(
            "[bright_green bold]ALL CHECKS PASSED[/bright_green bold]\n\n"
            "You're ready to go. Run:\n"
            "  python cli.py watch             # V2: Event-driven pipeline\n"
            "  python cli.py run               # V1: Synchronous pipeline\n"
            "  python cli.py dashboard          # Live terminal dashboard\n"
            "  python cli.py backtest           # Validate strategy\n"
            "  python cli.py watch --live       # Real trading (careful!)",
            style="bright_green",
        ))
    else:
        console.print(Panel(
            "[yellow bold]SOME CHECKS FAILED[/yellow bold]\n\n"
            "Fix the issues above, then run: python cli.py verify",
            style="yellow",
        ))


def cmd_verify_live(args):
    """Pre-flight check for live trading — validates keys, auth, balance. No orders."""
    from verify_live import run_verify_live
    run_verify_live()


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
        table.add_row(m.category, m.question[:60], f"{m.yes_price:.2f}", f"{m.no_price:.2f}", f"${m.volume:,.0f}")

    console.print(table)


def cmd_trades(args):
    import logger

    trades = logger.get_recent_trades(limit=args.limit)
    if not trades:
        console.print("[yellow]No trades logged yet.[/yellow]")
        return

    console.print(f"\n[bold]Last {len(trades)} trades[/bold]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", justify="right", width=4)
    table.add_column("Market", max_width=35)
    table.add_column("Signal", width=8)
    table.add_column("Mat.", justify="right", width=5)
    table.add_column("Side", width=4)
    table.add_column("Edge", justify="right", width=6)
    table.add_column("Bet", justify="right", width=7)
    table.add_column("Src", width=6)
    table.add_column("Lat.", justify="right", width=6)
    table.add_column("Status", width=8)

    for t in trades:
        cls = t.get("classification") or "—"
        mat = f"{t.get('materiality', 0) or 0:.2f}"
        src = (t.get("news_source") or "—")[:6]
        lat = f"{t.get('total_latency_ms') or 0}ms"
        table.add_row(
            str(t["id"]),
            t["market_question"][:35],
            cls[:8],
            mat,
            t["side"],
            f"{t['edge']:.1%}",
            f"${t['amount_usd']:.2f}",
            src,
            lat,
            t["status"][:8],
        )

    console.print(table)


def cmd_stats(args):
    import logger

    stats = logger.get_trade_stats()
    daily = logger.get_daily_pnl()
    latency = logger.get_latency_stats()
    cal = logger.get_calibration_stats()

    console.print(f"\n[bold]Pipeline Statistics[/bold]\n")
    console.print(f"  Total signals: {stats['total_trades']}")
    console.print(f"  Daily exposure: ${abs(daily):.2f}")
    console.print(f"  By status:")
    for status, count in stats["by_status"].items():
        console.print(f"    {status}: {count}")

    if latency["count"] > 0:
        console.print(f"\n  [bold]Latency:[/bold]")
        console.print(f"    Avg total: {latency['avg_total_ms']}ms")
        console.print(f"    Avg news: {latency['avg_news_ms']}ms")
        console.print(f"    Avg classification: {latency['avg_class_ms']}ms")

    if cal["total"] > 0:
        console.print(f"\n  [bold]Calibration:[/bold]")
        console.print(f"    Accuracy: {cal['accuracy']:.1f}% ({cal['total']} resolved)")


def main():
    parser = argparse.ArgumentParser(description="Polymarket Pipeline V2")
    sub = parser.add_subparsers(dest="command")

    # watch (V2)
    p_watch = sub.add_parser("watch", help="V2: Event-driven pipeline (real-time)")
    p_watch.add_argument("--live", action="store_true", help="Enable live trading")
    p_watch.add_argument("--threshold", type=float, default=None, help="Materiality threshold override")
    p_watch.set_defaults(func=cmd_watch)

    # run (V1)
    p_run = sub.add_parser("run", help="V1: Synchronous pipeline (RSS-based)")
    p_run.add_argument("--live", action="store_true", help="Enable live trading")
    p_run.add_argument("--max", type=int, default=10, help="Max markets to scan")
    p_run.add_argument("--hours", type=int, default=6, help="News lookback hours")
    p_run.add_argument("--threshold", type=float, default=None, help="Edge threshold override")
    p_run.set_defaults(func=cmd_run)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch live terminal dashboard")
    p_dash.add_argument("--speed", type=float, default=60.0, help="Seconds between scan cycles")
    p_dash.set_defaults(func=cmd_dashboard)

    # bot (market-data trading bot)
    p_bot = sub.add_parser("bot", help="Market-data trading bot (no paid API keys)")
    p_bot.add_argument("--live", action="store_true", help="Place real orders (needs credentials)")
    p_bot.add_argument("--loop", action="store_true", help="Run continuously")
    p_bot.add_argument("--cycles", type=int, default=1, help="Number of cycles (ignored with --loop)")
    p_bot.add_argument("--interval", type=float, default=None, help="Seconds between cycles")
    p_bot.add_argument("--bankroll", type=float, default=None, help="Reset paper bankroll before running")
    p_bot.add_argument("--strategies", type=str, default=None, help="Comma-separated strategy names")
    p_bot.set_defaults(func=cmd_bot)

    # portfolio
    p_pf = sub.add_parser("portfolio", help="Show bot paper-trading portfolio")
    p_pf.add_argument("--reset", type=float, nargs="?", const=0, default=None,
                      help="Reset portfolio (optionally to a given bankroll)")
    p_pf.set_defaults(func=cmd_portfolio)

    # backtest (V2 classification pipeline)
    p_bt = sub.add_parser("backtest", help="Backtest V2 news/classification strategy")
    p_bt.add_argument("--limit", type=int, default=30, help="Number of resolved markets")
    p_bt.add_argument("--category", type=str, default=None, help="Filter by category")
    p_bt.set_defaults(func=cmd_backtest)

    # botbacktest (market-data strategies)
    p_bbt = sub.add_parser("botbacktest", help="Backtest bot strategies over historical prices")
    p_bbt.add_argument("--limit", type=int, default=40, help="Number of resolved markets")
    p_bbt.add_argument("--category", type=str, default=None, help="Filter by question text")
    p_bbt.add_argument("--stake", type=float, default=10.0, help="Stake per simulated trade")
    p_bbt.add_argument("--strategies", type=str, default=None, help="Comma-separated strategy names")
    p_bbt.set_defaults(func=cmd_botbacktest)

    # calibrate
    p_cal = sub.add_parser("calibrate", help="Show classification accuracy report")
    p_cal.set_defaults(func=cmd_calibrate)

    # niche
    p_niche = sub.add_parser("niche", help="Browse niche markets (volume-filtered)")
    p_niche.set_defaults(func=cmd_niche)

    # verify
    p_verify = sub.add_parser("verify", help="Check API keys and connections")
    p_verify.set_defaults(func=cmd_verify)

    # verify-live
    p_vl = sub.add_parser("verify-live", help="Pre-flight check for live trading (no orders placed)")
    p_vl.set_defaults(func=cmd_verify_live)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Test the news scraper")
    p_scrape.add_argument("--hours", type=int, default=6, help="Lookback hours")
    p_scrape.set_defaults(func=cmd_scrape)

    # markets
    p_markets = sub.add_parser("markets", help="View all available markets")
    p_markets.add_argument("--max", type=int, default=50, help="Max markets to fetch")
    p_markets.set_defaults(func=cmd_markets)

    # trades
    p_trades = sub.add_parser("trades", help="View trade log")
    p_trades.add_argument("--limit", type=int, default=20, help="Number of trades to show")
    p_trades.set_defaults(func=cmd_trades)

    # stats
    p_stats = sub.add_parser("stats", help="Performance statistics")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
