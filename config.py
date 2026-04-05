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

# --- RSS Feeds ---
RSS_FEEDS = [
    # General / Breaking
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    # Crypto / Finance
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # Tech
    "https://feeds.feedburner.com/TechCrunch",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    # Sports (uncomment to enable)
    # "https://www.espn.com/espn/rss/news",
    # Science
    # "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
]

# --- Pipeline Settings ---
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "25"))
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "100"))
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.10"))
NEWS_LOOKBACK_HOURS = 6

# --- V2 Settings ---
MAX_VOLUME_USD = float(os.getenv("MAX_VOLUME_USD", "2000000"))
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "1000"))
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.6"))
SPEED_TARGET_SECONDS = float(os.getenv("SPEED_TARGET_SECONDS", "5"))
CLAUDE_MODEL = "claude-sonnet-4-6"
CLASSIFICATION_MODEL = "claude-haiku-4-5-20251001"
SCORING_MODEL = "claude-sonnet-4-6"

# --- Exit Strategy ---
TAKE_PROFIT_MULTIPLIER = float(os.getenv("TAKE_PROFIT_MULTIPLIER", "2.0"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.50"))
POSITION_CHECK_INTERVAL = float(os.getenv("POSITION_CHECK_INTERVAL", "30"))

# --- Categories to track (uncomment to enable) ---
MARKET_CATEGORIES = [
    "crypto",
    "ai",
    "technology",
    # "politics",
    # "science",
    # "sports",
    # "entertainment",
    # "economics",
    # "finance",
    # "geopolitics",
    # "elections",
    # "climate",
    # "health",
    # "legal",
    # "culture",
]

# --- Twitter filter keywords (for filtered stream rules) ---
TWITTER_KEYWORDS = [
    # Crypto
    "Bitcoin", "Ethereum", "Solana", "crypto", "SEC crypto", "Coinbase",
    "DeFi", "NFT", "stablecoin", "Binance", "memecoin",
    # AI / Tech
    "OpenAI", "GPT-5", "Anthropic", "Claude", "Google AI", "Gemini",
    "Apple", "NVIDIA", "Microsoft", "Google", "Meta AI",
    # Macro / Finance (crypto-adjacent)
    "Fed rate", "tariff", "interest rate", "CPI", "inflation",
    # Uncomment to expand:
    # "Congress", "White House", "Trump", "Biden", "NATO", "Ukraine",
    # "sanctions", "election", "S&P 500", "recession", "treasury",
    # "NFL", "NBA", "UFC", "FIFA", "Super Bowl", "Champions League",
    # "Oscar", "Grammy", "box office", "Netflix",
    # "NASA", "SpaceX", "Starship", "FDA", "WHO", "climate",
]
