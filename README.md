# Polymarket Pipeline V2

An AI-powered breaking news detector that classifies events against prediction markets and trades automatically when it finds edge.

```
Breaking News (Twitter / Telegram / RSS)
        ↓ (< 5 seconds)
Match to niche markets (< $500K volume)
        ↓
Claude Classification: bullish / bearish / neutral + materiality
        ↓
Edge detection + quarter-Kelly sizing
        ↓
Instant execution → SQLite log → calibration tracking
```

## What Changed From V1

V1 scraped RSS feeds (5-60 min delay), asked Claude "what's the probability?" (wrong question for LLMs), and competed on high-volume markets (where every bot already operates).

V2 inverts all three:
- **Speed**: Real-time Twitter/Telegram streams instead of stale RSS
- **Classification**: Claude classifies "bullish or bearish?" instead of estimating probability — a task LLMs are actually good at
- **Niche markets**: Only trades markets under $500K volume where the crowd is small and slow

---

## Setup (2 minutes)

### One-Command Setup

```bash
git clone https://github.com/brodyautomates/polymarket-pipeline.git
cd polymarket-pipeline
bash setup.sh
```

### Manual Setup

```bash
git clone https://github.com/brodyautomates/polymarket-pipeline.git
cd polymarket-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your keys to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...         # Required
TWITTER_BEARER_TOKEN=...             # Optional — real-time news stream
TELEGRAM_BOT_TOKEN=...               # Optional — channel monitoring
POLYMARKET_API_KEY=...               # Optional — live trading only
```

### Verify

```bash
python cli.py verify
```

---

## How to Use

### Market-Data Trading Bot (No API keys required)

The quickest way to see a working bot. It trades purely on live Polymarket
order-book data — **no Anthropic, Twitter, or Telegram keys needed** — and
paper-trades against a persistent portfolio by default.

```bash
# One cycle, paper trading, $1,000 starting bankroll
python cli.py bot --bankroll 1000

# Run continuously (default 60s between cycles)
python cli.py bot --loop

# Choose strategies and pace
python cli.py bot --loop --interval 30 --strategies favorite_longshot

# Inspect the paper portfolio and open positions
python cli.py portfolio

# Live trading (requires POLYMARKET_PRIVATE_KEY + POLYMARKET_FUNDER_ADDRESS)
python cli.py bot --live --loop
```

**How it works**

1. **Fetch** — pulls active markets from Polymarket's public Gamma API and keeps
   those inside the volume window (`MIN_VOLUME_USD`–`MAX_VOLUME_USD`).
2. **Strategy engine** (`strategy.py`) — runs one or more built-in strategies:
   - `favorite_longshot` — exploits the favorite-longshot bias by buying
     underpriced favorites (price band `0.85`–`0.97`) on liquid, tight-spread
     markets that resolve within a bounded horizon.
   - `mean_reversion` — records a rolling price history and buys the cheap side
     when price deviates from its short moving average, betting on reversion.
3. **Risk limits** — per-position cap (`MAX_POSITION_PCT`, `MAX_BET_USD`), total
   exposure cap (`MAX_EXPOSURE_PCT`), and a max open-position count. Spread and
   liquidity filters skip markets that are too thin to trade.
4. **Execution** — paper by default via a real ledger (`portfolio.py`: cash,
   positions, average price, realized + mark-to-market unrealized P&L). With
   `--live` it places CLOB orders through `executor.py`.
5. **Exits** — take-profit / stop-loss relative to entry price, plus a
   near-certain capture as a market approaches resolution.

Everything is persisted in `trades.db`, so `python cli.py portfolio` shows live
P&L across runs. Reset any time with `python cli.py portfolio --reset 1000`.

### Going Live (real orders)

Live trading is off by default. Before risking a cent, run the pre-flight check —
it validates your credentials, authenticates with the CLOB, and reads your
balance **without placing any order**:

```bash
python cli.py verify-live
```

Requirements (all in your local `.env`, which is gitignored — never commit keys):

| Variable | What it is |
|---|---|
| `POLYMARKET_PRIVATE_KEY` | Your wallet's **64-hex signing key** (`0x…`). **Not** the API-key UUID — that's a common, costly mix-up `verify-live` catches for you. |
| `POLYMARKET_FUNDER_ADDRESS` | The proxy wallet address holding your USDC (from the Polymarket deposit page). |
| `POLYMARKET_SIGNATURE_TYPE` | `0` = EOA (no proxy), `1` = email/magic login, `2` = browser-wallet (MetaMask) proxy. Funds deposited via polymarket.com sit in a proxy, so most users need `1` or `2`. |
| `DRY_RUN` | Set to `false` to arm live orders. |

```bash
pip install py-clob-client
# Prove the plumbing with a $1 cap before scaling up:
MAX_BET_USD=1 python cli.py bot --live
```

The API key/secret/passphrase are derived automatically from your private key —
you don't set them manually.

> ⚠️ The included strategies did **not** beat trading costs in a 1,000-market
> backtest (+1.6% ROI before fees). Live trading works mechanically, but treat
> these as a foundation to improve, not a proven money-maker. Start tiny.

### V2: Event-Driven Pipeline (news + Claude)

```bash
# Start the real-time pipeline — monitors news streams, classifies, trades
python cli.py watch

# Enable live trading
python cli.py watch --live
```

The `watch` command runs indefinitely. It connects to your configured news sources (Twitter, Telegram, RSS fallback), matches breaking headlines to niche Polymarket markets, classifies each with Claude, and executes trades when it finds edge.

### V1: Synchronous Pipeline

```bash
# Single scan — scrape RSS, score markets, log signals
python cli.py run

python cli.py run --max 15 --hours 12
```

### Live Dashboard

```bash
python cli.py dashboard
```

### Backtest

```bash
# Validate the V2 strategy against resolved markets
python cli.py backtest

python cli.py backtest --limit 50 --category ai
```

### All Commands

| Command | What it does |
|---|---|
| `python cli.py watch` | V2: Real-time event-driven pipeline |
| `python cli.py run` | V1: Synchronous RSS-based pipeline |
| `python cli.py dashboard` | Live terminal dashboard |
| `python cli.py backtest` | Backtest against resolved markets |
| `python cli.py calibrate` | Classification accuracy report |
| `python cli.py niche` | Browse niche markets (volume-filtered) |
| `python cli.py verify` | Check all API keys and connections |
| `python cli.py scrape` | Test news scraper |
| `python cli.py markets` | Browse all active markets |
| `python cli.py trades` | View trade log |
| `python cli.py stats` | Performance + latency + calibration stats |

---

## Architecture

### V2 Pipeline (Event-Driven)

```
news_stream.py      Real-time news — Twitter API v2, Telegram, RSS fallback
market_watcher.py   Polymarket WebSocket — live prices, niche filter, momentum
classifier.py       Claude classification — bullish/bearish/neutral + materiality
matcher.py          Routes breaking news to relevant markets
edge.py             Edge detection + Kelly sizing (V2: classification-based)
executor.py         Trade execution — dry-run + live CLOB orders (async)
pipeline.py         Event-driven orchestrator (asyncio)
calibrator.py       Tracks classification accuracy over time
backtest.py         Historical replay for strategy validation
```

### Market-Data Trading Bot (no API keys)

```
bot.py              Trading loop — fetch → strategy → risk limits → execute → manage exits
strategy.py         Strategy engine — favorite-longshot bias, mean-reversion
portfolio.py        Paper-trading ledger — cash, positions, realized + unrealized P&L
```

### Shared Infrastructure

```
logger.py           SQLite — trades, news events, calibration, latency tracking
config.py           All settings, API keys, thresholds
dashboard.py        Bloomberg Terminal-style live dashboard
cli.py              CLI — watch, run, backtest, calibrate, niche, verify, etc.
```

---

## How It Actually Works

### 1. News Detection
Real-time streams from Twitter (filtered by keywords: OpenAI, Bitcoin, Fed rate, etc.), Telegram channels, and RSS fallback. Events are deduplicated and timestamped with receive latency.

### 2. Market Matching
Each headline is matched to active niche markets (<$500K volume) by keyword overlap. Only relevant markets proceed to classification.

### 3. Classification (The Key Shift)
Instead of "what's the probability?", Claude is asked: *"Does this news make the market MORE likely to resolve YES, MORE likely to resolve NO, or is it NOT RELEVANT?"*

This is a classification task — something LLMs are genuinely good at. Claude also rates materiality (0-1): how much should this move the price?

### 4. Edge Detection
If direction is bullish/bearish AND materiality exceeds threshold (default 0.6) AND the market price has room to move — that's a signal. Position sizing uses quarter-Kelly.

### 5. Execution
Dry-run by default. Live mode places orders via Polymarket CLOB API. Safety: $25 max bet, $100 daily limit.

### 6. Calibration
Every trade is tracked. As markets resolve, the system measures whether its classifications were correct. Accuracy by source and category informs future confidence.

---

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `DRY_RUN` | `true` | Set to `false` for live trading |
| `MAX_BET_USD` | `25` | Maximum single bet |
| `DAILY_LOSS_LIMIT_USD` | `100` | Pipeline halts if breached |
| `EDGE_THRESHOLD` | `0.10` | Minimum edge to trigger trade |
| `MAX_VOLUME_USD` | `500000` | Only trade markets below this volume |
| `MIN_VOLUME_USD` | `1000` | Skip dead markets |
| `MATERIALITY_THRESHOLD` | `0.6` | Minimum materiality to act on |
| `SPEED_TARGET_SECONDS` | `5` | Target news-to-trade latency |

---

## Safety

- Dry-run mode ON by default
- $25 max single bet, $100 daily limit
- Quarter-Kelly position sizing
- Niche market filter prevents competing against sophisticated bots
- Calibration tracking — auto-detects if strategy accuracy drops
- All API keys in `.env`, never committed

---

Built by [@brodyautomates](https://github.com/brodyautomates)

---

## Disclaimer

This project is for **entertainment and educational purposes only**. It is not financial advice. The authors are not responsible for any financial losses incurred through the use of this software. Prediction market trading carries significant risk — you can lose money. Never trade with funds you cannot afford to lose. Past performance of any strategy does not guarantee future results. Use at your own risk.
