# Polymarket Pipeline

A Claude-powered news scraper that scores confidence on Polymarket events and places bets automatically when it finds edge.

```
News RSS Feeds → Claude Confidence Scoring → Edge Detection → Auto Trade Execution
```

## What It Does

1. **Scrapes** real-time news from 5 RSS feeds (Google News, TechCrunch, Reuters, Ars Technica, NYT)
2. **Fetches** active Polymarket prediction markets with real liquidity
3. **Scores** each market using Claude — "Given these headlines, what's the probability this resolves YES?"
4. **Detects edge** when Claude's confidence diverges from market price by ≥10%
5. **Executes trades** automatically (dry-run by default, live via Polymarket CLOB API)
6. **Logs everything** to SQLite — full audit trail of bets, reasoning, and outcomes

## Live Dashboard

Bloomberg Terminal-style interface that shows the pipeline running in real-time.

```bash
python cli.py dashboard
```

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  POLYMARKET PIPELINE        NEWS SCRAPER + AI CONFIDENCE SCORER + AUTO TRADER ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
╭─ PIPELINE STATUS ─────────╮╭─ MARKET SCANNER ─────────────────────────────────╮
│ ● Pipeline ACTIVE         ││ Will OpenAI release GPT-5  Mkt:0.62  Claude:0.78│
│ Scan Cycle: #14           ││ > EDGE: +16%  BUY YES $25            ✓ WON +$15 │
│ Signals today: 7          ││ Bitcoin exceed $150k       Mkt:0.34  Claude:0.31│
│ Win rate: 68.2%           ││ > no edge                                       │
├─ PERFORMANCE ─────────────┤├─ TRADE LOG ─────────────────────────────────────-┤
│ PnL: +$142.80             ││ 14:32 BUY YES $15 OpenAI GPT-5...     ✓ WON    │
│ ROI: +28.6%               ││ 14:28 BUY NO  $20 Fed rate cut...     ● OPEN   │
│ 12W / 4L / 3P             ││ 13:45 BUY YES $25 ETH $4k...         ✗ LOST   │
│ Avg Edge: 14.2%           ││ 13:12 BUY YES $10 Trump tariffs...    ✓ WON    │
╰───────────────────────────╯╰─────────────────────────────────────────────────╯
```

## Quick Start

```bash
git clone https://github.com/brodyautomates/polymarket-pipeline.git
cd polymarket-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Demo mode (no API keys needed)
python cli.py dashboard

# Real pipeline (needs Anthropic API key)
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
python cli.py run
```

## CLI Commands

| Command | What it does |
|---|---|
| `python cli.py dashboard` | Live terminal dashboard (demo mode) |
| `python cli.py dashboard --speed 5` | Faster scan cycles |
| `python cli.py run` | Run real pipeline (dry-run) |
| `python cli.py run --live` | Run with live trading |
| `python cli.py scrape` | Test news scraper |
| `python cli.py markets` | Browse active Polymarket markets |
| `python cli.py trades` | View trade log |
| `python cli.py stats` | Performance statistics |

## Architecture

```
scraper.py     → RSS + NewsAPI ingestion
markets.py     → Polymarket Gamma API + CLOB fallback
scorer.py      → Claude confidence scoring
edge.py        → Edge detection + Kelly criterion sizing
executor.py    → Trade execution (dry-run + live)
logger.py      → SQLite trade log
pipeline.py    → Full pipeline orchestrator
dashboard.py   → Live terminal UI
mock_api.py    → Realistic demo data engine
cli.py         → CLI interface
```

## Safety

- Dry-run mode ON by default
- $25 max single bet
- $100 daily loss limit
- Quarter-Kelly position sizing
- All API keys in `.env`, never committed

## Requirements

- Python 3.9+
- Anthropic API key (for real scoring)
- Polymarket account + API credentials (for live trading, needs Python 3.9.10+)
