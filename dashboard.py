#!/usr/bin/env python3
"""
Polymarket Pipeline — Live Terminal Dashboard
Bloomberg Terminal aesthetic. Runs mock data for demo.
"""
from __future__ import annotations

import time
import sys
import random
from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box

import mock_api

console = Console()

# --- Color Palette ---
ACCENT = "bright_green"
DIM = "bright_black"
WARN = "yellow"
LOSS = "red"
WIN = "bright_green"
HEADER = "bold bright_cyan"
MUTED = "dim white"


def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=2),
    )
    layout["left"].split_column(
        Layout(name="status", ratio=1),
        Layout(name="performance", ratio=1),
    )
    layout["right"].split_column(
        Layout(name="scanner", ratio=2),
        Layout(name="trades", ratio=3),
    )
    return layout


def render_header() -> Panel:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)
    grid.add_row(
        Text(" POLYMARKET PIPELINE", style="bold bright_green"),
        Text("NEWS SCRAPER + AI CONFIDENCE SCORER + AUTO TRADER", style=DIM),
        Text(f"{now} ", style=MUTED),
    )
    return Panel(grid, style="bright_green", box=box.HEAVY)


def render_status(cycle: dict | None) -> Panel:
    perf = cycle["performance"] if cycle else mock_api.get_performance()
    run = cycle["run_number"] if cycle else 0

    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("label", style=MUTED, width=18)
    table.add_column("value", style=ACCENT)

    status_dot = "[bright_green]●[/bright_green]" if cycle else "[yellow]○[/yellow]"
    table.add_row("Pipeline", f"{status_dot} ACTIVE")
    table.add_row("Scan Cycle", f"#{run}")
    table.add_row("Markets Scanned", str(cycle["markets_scanned"]) if cycle else "—")
    table.add_row("Headlines Found", str(cycle["headlines_ingested"]) if cycle else "—")
    table.add_row("Signals / Trades", f"{cycle['signals_found']} / {cycle['trades_executed']}" if cycle else "— / —")
    table.add_row("", "")
    table.add_row("Edge Threshold", "≥ 10%")
    table.add_row("Max Bet", "$25.00")
    table.add_row("Daily Limit", "$100.00")
    table.add_row("Mode", "[bright_green]LIVE[/bright_green]")

    return Panel(table, title="[bold]PIPELINE STATUS[/bold]", border_style="bright_green", box=box.ROUNDED)


def render_performance(cycle: dict | None) -> Panel:
    perf = cycle["performance"] if cycle else mock_api.get_performance()

    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("label", style=MUTED, width=18)
    table.add_column("value")

    # PnL color
    pnl = perf["total_pnl"]
    pnl_style = WIN if pnl >= 0 else LOSS
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

    roi = perf["roi"]
    roi_style = WIN if roi >= 0 else LOSS

    wr = perf["win_rate"]
    wr_style = WIN if wr >= 55 else (WARN if wr >= 45 else LOSS)

    table.add_row("Total Trades", f"[{ACCENT}]{perf['total_trades']}[/{ACCENT}]")
    table.add_row("Win / Loss / Open", f"[{WIN}]{perf['wins']}W[/{WIN}] [{LOSS}]{perf['losses']}L[/{LOSS}] [{WARN}]{perf['pending']}P[/{WARN}]")
    table.add_row("Win Rate", f"[{wr_style}]{wr:.1f}%[/{wr_style}]")
    table.add_row("", "")
    table.add_row("Total PnL", f"[{pnl_style}]{pnl_str}[/{pnl_style}]")
    table.add_row("ROI", f"[{roi_style}]{roi:+.1f}%[/{roi_style}]")
    table.add_row("Total Wagered", f"[{ACCENT}]${perf['total_wagered']:.2f}[/{ACCENT}]")
    table.add_row("Avg Edge", f"[{ACCENT}]{perf['avg_edge']:.1f}%[/{ACCENT}]")
    table.add_row("", "")
    table.add_row("Best Trade", f"[{WIN}]+${perf['best_trade']:.2f}[/{WIN}]")
    table.add_row("Worst Trade", f"[{LOSS}]-${abs(perf['worst_trade']):.2f}[/{LOSS}]")

    return Panel(table, title="[bold]PERFORMANCE[/bold]", border_style="bright_cyan", box=box.ROUNDED)


def render_scanner(cycle: dict | None) -> Panel:
    if not cycle or not cycle["signals"]:
        content = Table(show_header=True, box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        content.add_column("Market", style=MUTED, max_width=42)
        content.add_column("Mkt$", justify="right", style=MUTED)
        content.add_column("Claude", justify="right", style=ACCENT)
        content.add_column("Edge", justify="right")
        content.add_column("Signal", justify="center")

        if cycle and cycle["markets"]:
            for m in cycle["markets"][:8]:
                score = mock_api.score_market(m["question"], m["yes_price"], [])
                edge_val = score["edge"]
                edge_style = WIN if edge_val >= 0.10 else DIM
                signal = f"[{WIN}]► BUY[/{WIN}]" if edge_val >= 0.10 else f"[{DIM}]—[/{DIM}]"
                content.add_row(
                    m["question"][:42],
                    f"{m['yes_price']:.2f}",
                    f"{score['confidence']:.2f}",
                    f"[{edge_style}]{edge_val:.0%}[/{edge_style}]",
                    signal,
                )
        else:
            content.add_row("[dim]Waiting for scan...[/dim]", "", "", "", "")

        return Panel(content, title="[bold]MARKET SCANNER[/bold]  ·  Claude Confidence vs Market Odds", border_style="bright_green", box=box.ROUNDED)

    # Show active signals with detail
    content = Table(show_header=True, box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    content.add_column("Market", max_width=38)
    content.add_column("Mkt$", justify="right", width=5)
    content.add_column("Claude", justify="right", width=6, style=ACCENT)
    content.add_column("Edge", justify="right", width=6)
    content.add_column("Side", justify="center", width=5)
    content.add_column("Bet", justify="right", width=7)
    content.add_column("Result", justify="center", width=8)

    # First show signals from this cycle
    for sig in cycle["signals"][:5]:
        m = sig["market"]
        s = sig["score"]
        t = sig["trade"]
        edge_pct = f"{s['edge']:.0%}"
        side_style = WIN if t["side"] == "YES" else "bright_magenta"

        if t["status"] == "won":
            result = f"[{WIN}]✓ +${t['pnl']:.0f}[/{WIN}]"
        elif t["status"] == "lost":
            result = f"[{LOSS}]✗ -${abs(t['pnl']):.0f}[/{LOSS}]"
        else:
            result = f"[{WARN}]● OPEN[/{WARN}]"

        content.add_row(
            m["question"][:38],
            f"{m['yes_price']:.2f}",
            f"{s['confidence']:.2f}",
            f"[{WIN}]{edge_pct}[/{WIN}]",
            f"[{side_style}]{t['side']}[/{side_style}]",
            f"${t['amount']:.0f}",
            result,
        )

    # Fill remaining rows with non-signal markets
    non_signals = [m for m in cycle["markets"] if not any(
        sig["market"]["question"] == m["question"] for sig in cycle["signals"]
    )]
    for m in non_signals[:max(0, 8 - len(cycle["signals"])):]:
        score = mock_api.score_market(m["question"], m["yes_price"], [])
        content.add_row(
            f"[{DIM}]{m['question'][:38]}[/{DIM}]",
            f"[{DIM}]{m['yes_price']:.2f}[/{DIM}]",
            f"[{DIM}]{score['confidence']:.2f}[/{DIM}]",
            f"[{DIM}]{score['edge']:.0%}[/{DIM}]",
            f"[{DIM}]—[/{DIM}]",
            f"[{DIM}]—[/{DIM}]",
            f"[{DIM}]no edge[/{DIM}]",
        )

    return Panel(content, title="[bold]MARKET SCANNER[/bold]  ·  Claude Confidence vs Market Odds", border_style="bright_green", box=box.ROUNDED)


def render_trades() -> Panel:
    trades = mock_api.get_recent_trades(count=10)

    table = Table(show_header=True, box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    table.add_column("Time", width=8, style=MUTED)
    table.add_column("Market", max_width=40)
    table.add_column("Side", justify="center", width=5)
    table.add_column("Bet", justify="right", width=7)
    table.add_column("Edge", justify="right", width=6)
    table.add_column("Claude", justify="right", width=6)
    table.add_column("Mkt$", justify="right", width=5)
    table.add_column("PnL", justify="right", width=9)
    table.add_column("Status", justify="center", width=8)

    if not trades:
        table.add_row("[dim]No trades yet — pipeline scanning...[/dim]", "", "", "", "", "", "", "", "")
    else:
        for t in trades:
            side_style = WIN if t["side"] == "YES" else "bright_magenta"

            if t["status"] == "won":
                pnl_str = f"[{WIN}]+${t['pnl']:.2f}[/{WIN}]"
                status_str = f"[{WIN}]✓ WON[/{WIN}]"
            elif t["status"] == "lost":
                pnl_str = f"[{LOSS}]-${abs(t['pnl']):.2f}[/{LOSS}]"
                status_str = f"[{LOSS}]✗ LOST[/{LOSS}]"
            else:
                pnl_str = f"[{WARN}]$0.00[/{WARN}]"
                status_str = f"[{WARN}]● OPEN[/{WARN}]"

            table.add_row(
                t["time_str"],
                t["question"][:40],
                f"[{side_style}]{t['side']}[/{side_style}]",
                f"${t['amount']:.2f}",
                f"{t['edge']:.0%}",
                f"{t['claude_score']:.2f}",
                f"{t['market_price']:.2f}",
                pnl_str,
                status_str,
            )

    return Panel(table, title="[bold]TRADE LOG[/bold]  ·  Bets Placed by Pipeline", border_style="bright_cyan", box=box.ROUNDED)


def render_footer(cycle: dict | None) -> Panel:
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=2)
    grid.add_column(justify="center", ratio=3)
    grid.add_column(justify="right", ratio=2)

    # Latest headline ticker
    if cycle and cycle["headlines"]:
        h = cycle["headlines"][0]
        headline_text = f"[{ACCENT}]►[/{ACCENT}] [{MUTED}]{h['source']}:[/{MUTED}] {h['headline'][:80]}"
    else:
        headline_text = f"[{DIM}]Waiting for news feed...[/{DIM}]"

    perf = cycle["performance"] if cycle else mock_api.get_performance()
    pnl = perf["total_pnl"]
    pnl_style = WIN if pnl >= 0 else LOSS
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

    grid.add_row(
        headline_text,
        f"[{DIM}]Ctrl+C to exit[/{DIM}]",
        f"PnL: [{pnl_style}]{pnl_str}[/{pnl_style}]  |  Trades: [{ACCENT}]{perf['total_trades']}[/{ACCENT}] ",
    )
    return Panel(grid, style="bright_green", box=box.HEAVY)


def run_dashboard(scan_interval: float = 8.0, seed_cycles: int = 3):
    """Launch the live dashboard."""

    # Seed with some initial trades so it doesn't start empty
    for _ in range(seed_cycles):
        mock_api.run_scan_cycle()
        time.sleep(0.05)

    layout = make_layout()
    latest_cycle = mock_api.run_scan_cycle()

    layout["header"].update(render_header())
    layout["status"].update(render_status(latest_cycle))
    layout["performance"].update(render_performance(latest_cycle))
    layout["scanner"].update(render_scanner(latest_cycle))
    layout["trades"].update(render_trades())
    layout["footer"].update(render_footer(latest_cycle))

    try:
        with Live(layout, console=console, refresh_per_second=2, screen=True) as live:
            last_scan = time.time()
            tick = 0

            while True:
                tick += 1
                now = time.time()

                # Run new scan cycle periodically
                if now - last_scan >= scan_interval:
                    latest_cycle = mock_api.run_scan_cycle()
                    last_scan = now

                # Update all panels
                layout["header"].update(render_header())
                layout["status"].update(render_status(latest_cycle))
                layout["performance"].update(render_performance(latest_cycle))
                layout["scanner"].update(render_scanner(latest_cycle))
                layout["trades"].update(render_trades())
                layout["footer"].update(render_footer(latest_cycle))

                time.sleep(0.5)

    except KeyboardInterrupt:
        console.print(f"\n[{ACCENT}]Pipeline stopped. {mock_api.state.trade_counter} trades logged.[/{ACCENT}]")


if __name__ == "__main__":
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    run_dashboard(scan_interval=interval)
