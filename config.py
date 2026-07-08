import os
from dotenv import load_dotenv

load_dotenv()

# --- Anthropic ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Polymarket CLOB ---
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", "")
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "")
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
# Funder is the Polymarket proxy (deposit) wallet address that holds your USDC.
POLYMARKET_FUNDER_ADDRESS = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
# Order signature type:
#   0 = EOA          — you sign and hold funds in the same wallet (no proxy)
#   1 = POLY_PROXY   — Polymarket email/magic login (embedded wallet)
#   2 = POLY_GNOSIS_SAFE — Polymarket browser-wallet (MetaMask) proxy
# Most web-app users are 1 or 2; funds deposited via polymarket.com sit in a proxy.
POLYMARKET_SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2"))
POLYMARKET_HOST = "https://clob.polymarket.com"
POLYMARKET_WS_HOST = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# --- Twitter API v2 ---
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_CHANNEL_IDS", "").split(",") if c.strip()
]

# --- NewsAPI (optional, RSS fallback) ---
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# --- RSS Feeds (fallback) ---
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=AI+artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.feedburner.com/TechCrunch",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
]

# --- Pipeline Settings ---
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "25"))
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "100"))
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.10"))
NEWS_LOOKBACK_HOURS = 6

# --- V2 Settings ---
MAX_VOLUME_USD = float(os.getenv("MAX_VOLUME_USD", "500000"))
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "1000"))
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.6"))
SPEED_TARGET_SECONDS = float(os.getenv("SPEED_TARGET_SECONDS", "5"))
CLASSIFICATION_MODEL = "claude-haiku-4-5-20251001"
SCORING_MODEL = "claude-sonnet-4-6-20250514"

# --- Market-Data Trading Bot (bot.py) ---
# Self-contained strategy engine. Needs NO paid API keys — trades on live
# Polymarket order-book data alone. Paper-trades by default.
STARTING_BANKROLL_USD = float(os.getenv("STARTING_BANKROLL_USD", "1000"))
BOT_STRATEGIES = [
    s.strip() for s in os.getenv(
        "BOT_STRATEGIES", "favorite_longshot,mean_reversion,momentum,arbitrage"
    ).split(",") if s.strip()
]
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.05"))   # max % of bankroll per position
MAX_EXPOSURE_PCT = float(os.getenv("MAX_EXPOSURE_PCT", "0.50"))   # max % of bankroll deployed at once
MAX_SPREAD = float(os.getenv("MAX_SPREAD", "0.04"))              # skip illiquid/wide markets
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))
BOT_LOOP_INTERVAL_SECONDS = float(os.getenv("BOT_LOOP_INTERVAL_SECONDS", "60"))

# Favorite-longshot strategy: buy underpriced favorites in this price band.
FAV_LONGSHOT_BAND = (
    float(os.getenv("FAV_MIN_PRICE", "0.85")),
    float(os.getenv("FAV_MAX_PRICE", "0.97")),
)
FAV_MAX_HOURS_TO_RESOLUTION = float(os.getenv("FAV_MAX_HOURS", "720"))  # 30 days

# Mean-reversion strategy: trade when price deviates from its recent average.
MEANREV_MIN_DEVIATION = float(os.getenv("MEANREV_MIN_DEVIATION", "0.05"))
MEANREV_WINDOW = int(os.getenv("MEANREV_WINDOW", "5"))

# Momentum strategy: follow a consistent move over the recent window.
MOMENTUM_WINDOW = int(os.getenv("MOMENTUM_WINDOW", "5"))
MOMENTUM_MIN_MOVE = float(os.getenv("MOMENTUM_MIN_MOVE", "0.05"))

# Arbitrage strategy: buy YES+NO when their asks sum below 1 (risk-free).
ARB_MIN_PROFIT = float(os.getenv("ARB_MIN_PROFIT", "0.01"))   # min profit per $1 pair
ARB_SCAN_LIMIT = int(os.getenv("ARB_SCAN_LIMIT", "40"))       # top-N liquid markets to probe

# --- Categories to track ---
MARKET_CATEGORIES = [
    "ai",
    "technology",
    "crypto",
    "politics",
    "science",
]

# --- Twitter filter keywords (for filtered stream rules) ---
TWITTER_KEYWORDS = [
    "OpenAI", "GPT-5", "Anthropic", "Claude", "Google AI", "Gemini",
    "Bitcoin", "Ethereum", "Solana", "crypto",
    "Fed rate", "tariff", "Congress", "White House",
    "SpaceX", "Starship", "NASA",
    "Apple", "NVIDIA", "Microsoft", "Google",
]
