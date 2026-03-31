"""
Mock API — generates realistic-looking pipeline data for demo purposes.
Simulates live market data, Claude scoring, trade execution, and performance.
"""
from __future__ import annotations

import random
import time
import hashlib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

# --- Realistic market questions (current events style) ---
MOCK_MARKETS = [
    {"q": "Will OpenAI release GPT-5 before August 2026?", "cat": "ai", "base_yes": 0.62, "vol": 4_800_000},
    {"q": "Will Bitcoin exceed $150,000 by end of 2026?", "cat": "crypto", "base_yes": 0.34, "vol": 12_300_000},
    {"q": "Will the Fed cut rates in July 2026?", "cat": "politics", "base_yes": 0.71, "vol": 8_200_000},
    {"q": "Will Anthropic raise at $100B+ valuation by Q3 2026?", "cat": "ai", "base_yes": 0.48, "vol": 2_100_000},
    {"q": "Will Trump impose new China tariffs before September?", "cat": "politics", "base_yes": 0.83, "vol": 6_700_000},
    {"q": "Will Ethereum flip Bitcoin in market cap by 2027?", "cat": "crypto", "base_yes": 0.08, "vol": 3_400_000},
    {"q": "Will Apple announce an AI chip partnership in 2026?", "cat": "technology", "base_yes": 0.55, "vol": 1_900_000},
    {"q": "Will SpaceX Starship complete orbital refueling by 2026?", "cat": "science", "base_yes": 0.29, "vol": 950_000},
    {"q": "Will a major AI lab face federal regulation by Q4 2026?", "cat": "ai", "base_yes": 0.67, "vol": 3_800_000},
    {"q": "Will Solana exceed $500 by end of 2026?", "cat": "crypto", "base_yes": 0.21, "vol": 5_600_000},
    {"q": "Will Google lose its search antitrust case appeal?", "cat": "technology", "base_yes": 0.44, "vol": 2_700_000},
    {"q": "Will US GDP growth exceed 3% in Q2 2026?", "cat": "politics", "base_yes": 0.38, "vol": 1_400_000},
    {"q": "Will Claude surpass ChatGPT in market share by 2027?", "cat": "ai", "base_yes": 0.19, "vol": 1_200_000},
    {"q": "Will NVIDIA stock split again in 2026?", "cat": "technology", "base_yes": 0.42, "vol": 4_100_000},
    {"q": "Will a humanoid robot ship commercially by end of 2026?", "cat": "ai", "base_yes": 0.57, "vol": 2_300_000},
]

MOCK_HEADLINES = [
    {"h": "OpenAI reportedly testing GPT-5 internally with select partners", "s": "The Information", "cat": "ai"},
    {"h": "Bitcoin ETF inflows hit $2.1B in single week, highest since launch", "s": "Bloomberg", "cat": "crypto"},
    {"h": "Fed minutes signal growing consensus for summer rate adjustment", "s": "Reuters", "cat": "politics"},
    {"h": "Anthropic closes $5B round led by Google, valuation undisclosed", "s": "TechCrunch", "cat": "ai"},
    {"h": "White House confirms new tariff framework targeting Chinese AI chips", "s": "WSJ", "cat": "politics"},
    {"h": "Ethereum L2 activity surges 340% as Dencun upgrade matures", "s": "CoinDesk", "cat": "crypto"},
    {"h": "Apple acquires edge AI startup for $400M, sources say", "s": "Bloomberg", "cat": "technology"},
    {"h": "SpaceX delays orbital refueling test to Q3 after valve issue", "s": "Ars Technica", "cat": "science"},
    {"h": "Bipartisan AI Safety Act advances to Senate floor vote", "s": "Politico", "cat": "ai"},
    {"h": "Solana network processes 100K TPS in stress test milestone", "s": "The Block", "cat": "crypto"},
    {"h": "Google appeals DOJ search ruling, cites innovation harm", "s": "NYT", "cat": "technology"},
    {"h": "Q1 GDP revised up to 2.8%, consumer spending drives growth", "s": "CNBC", "cat": "politics"},
    {"h": "Claude 4.5 benchmarks show 12% lead on coding tasks vs GPT-4o", "s": "VentureBeat", "cat": "ai"},
    {"h": "NVIDIA announces Blackwell Ultra, hints at 2026 stock action", "s": "The Verge", "cat": "technology"},
    {"h": "Figure AI demos warehouse robot completing 8-hour shift autonomously", "s": "IEEE Spectrum", "cat": "ai"},
    {"h": "SEC delays spot Ethereum ETF options decision to August", "s": "CoinTelegraph", "cat": "crypto"},
    {"h": "Microsoft reports 47% Azure AI revenue growth in Q2 earnings", "s": "Reuters", "cat": "technology"},
    {"h": "China retaliates with export controls on rare earth AI components", "s": "FT", "cat": "politics"},
    {"h": "Anthropic launches Claude Enterprise with SOC 2 compliance", "s": "TechCrunch", "cat": "ai"},
    {"h": "DeFi TVL crosses $200B for first time since 2021", "s": "DeFi Llama", "cat": "crypto"},
]

MOCK_REASONING = [
    "Recent headlines suggest strong momentum toward this outcome. Multiple credible sources report active development and regulatory tailwinds.",
    "Mixed signals — positive technical indicators but political headwinds create uncertainty. Market may be slightly overpricing YES.",
    "News flow strongly favors this outcome. Three independent sources confirm progress, and the timeline is achievable.",
    "Market appears to be underpricing based on recent developments. Insider activity and regulatory signals both point to higher probability.",
    "Bearish signals dominate recent coverage. Supply chain delays and competitive pressure suggest the market is correctly priced or slightly optimistic.",
    "Strong edge detected. The market hasn't yet priced in the latest announcement, creating a window before price adjusts.",
    "Moderate confidence. Base rates for this type of event suggest ~60% probability, but recent news pushes it higher.",
    "High-conviction signal. Convergence of technical, fundamental, and sentiment indicators all point the same direction.",
]


@dataclass
class MockState:
    """Holds mutable state for the mock simulation."""
    trade_counter: int = 0
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    pending: int = 0
    trades: list = field(default_factory=list)
    _price_cache: dict = field(default_factory=dict)
    _last_scan_time: float = 0.0
    run_number: int = 0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return (self.wins / total * 100) if total > 0 else 0.0

    @property
    def roi(self) -> float:
        total_risked = sum(t["amount"] for t in self.trades) or 1
        return (self.total_pnl / total_risked) * 100


state = MockState()


def _jitter(base: float, spread: float = 0.06) -> float:
    """Add realistic price jitter to a base value, clamped 0.01-0.99."""
    return max(0.01, min(0.99, base + random.uniform(-spread, spread)))


def _fake_order_id() -> str:
    raw = f"{time.time()}{random.randint(1000,9999)}"
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _fake_condition_id() -> str:
    raw = f"cond_{random.randint(100000, 999999)}"
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def get_live_markets(count: int = 8) -> list[dict]:
    """Return mock markets with drifting prices."""
    selected = random.sample(MOCK_MARKETS, min(count, len(MOCK_MARKETS)))
    markets = []
    for m in selected:
        key = m["q"]
        if key not in state._price_cache:
            state._price_cache[key] = m["base_yes"]
        # Drift price slightly each call
        state._price_cache[key] = _jitter(state._price_cache[key], 0.02)
        yes = round(state._price_cache[key], 2)
        markets.append({
            "condition_id": _fake_condition_id(),
            "question": m["q"],
            "category": m["cat"],
            "yes_price": yes,
            "no_price": round(1 - yes, 2),
            "volume": m["vol"] + random.randint(-50000, 50000),
        })
    return markets


def get_live_headlines(count: int = 6) -> list[dict]:
    """Return mock headlines with realistic timestamps."""
    selected = random.sample(MOCK_HEADLINES, min(count, len(MOCK_HEADLINES)))
    now = datetime.now(timezone.utc)
    headlines = []
    for i, h in enumerate(selected):
        age_minutes = random.randint(3, 180)
        headlines.append({
            "headline": h["h"],
            "source": h["s"],
            "category": h["cat"],
            "published_at": (now - timedelta(minutes=age_minutes)).isoformat(),
            "age_str": f"{age_minutes}m ago" if age_minutes < 60 else f"{age_minutes // 60}h {age_minutes % 60}m ago",
        })
    headlines.sort(key=lambda x: x["published_at"], reverse=True)
    return headlines


def score_market(question: str, market_price: float, headlines: list[dict]) -> dict:
    """Simulate Claude scoring a market."""
    # Generate a score that's somewhat correlated with market price but can diverge
    base = market_price
    divergence = random.uniform(-0.25, 0.25)
    score = max(0.03, min(0.97, base + divergence))

    return {
        "confidence": round(score, 2),
        "market_price": market_price,
        "edge": round(abs(score - market_price), 2),
        "reasoning": random.choice(MOCK_REASONING),
        "relevant_headlines": len([h for h in headlines if random.random() > 0.4]),
        "model": "claude-sonnet-4-6",
    }


def execute_mock_trade(question: str, side: str, amount: float, edge: float, claude_score: float, market_price: float) -> dict:
    """Simulate trade execution and outcome resolution."""
    state.trade_counter += 1
    order_id = _fake_order_id()
    now = datetime.now(timezone.utc)

    # Determine outcome — edge-weighted probability of winning
    # Higher edge = slightly better odds of winning (realistic but favorable for demo)
    win_prob = 0.55 + (edge * 0.8)  # 10% edge → 63% win rate, 20% edge → 71%
    won = random.random() < win_prob

    # Some trades still pending
    is_pending = random.random() < 0.2
    if is_pending:
        status = "open"
        pnl = 0.0
        result = "pending"
        state.pending += 1
    elif won:
        payout_mult = (1.0 / market_price) if side == "YES" else (1.0 / (1 - market_price))
        pnl = round(amount * (payout_mult - 1), 2)
        status = "won"
        result = "resolved_yes" if side == "YES" else "resolved_no"
        state.wins += 1
        state.total_pnl += pnl
    else:
        pnl = -amount
        status = "lost"
        result = "resolved_no" if side == "YES" else "resolved_yes"
        state.losses += 1
        state.total_pnl += pnl

    trade = {
        "id": state.trade_counter,
        "order_id": order_id,
        "question": question,
        "side": side,
        "amount": amount,
        "edge": edge,
        "claude_score": claude_score,
        "market_price": market_price,
        "status": status,
        "result": result,
        "pnl": pnl,
        "timestamp": now.isoformat(),
        "time_str": now.strftime("%H:%M:%S"),
    }
    state.trades.append(trade)
    return trade


def run_scan_cycle() -> dict:
    """Run one full pipeline scan cycle. Returns summary."""
    state.run_number += 1
    state._last_scan_time = time.time()

    markets = get_live_markets(count=random.randint(6, 10))
    headlines = get_live_headlines(count=random.randint(5, 8))
    signals = []
    trades_this_cycle = []

    for m in markets:
        score = score_market(m["question"], m["yes_price"], headlines)

        if score["edge"] >= 0.10:
            side = "YES" if score["confidence"] > m["yes_price"] else "NO"
            amount = round(min(25.0, max(5.0, score["edge"] * 250)), 2)

            trade = execute_mock_trade(
                question=m["question"],
                side=side,
                amount=amount,
                edge=score["edge"],
                claude_score=score["confidence"],
                market_price=m["yes_price"],
            )
            signals.append({
                "market": m,
                "score": score,
                "trade": trade,
            })
            trades_this_cycle.append(trade)

    return {
        "run_number": state.run_number,
        "markets_scanned": len(markets),
        "headlines_ingested": len(headlines),
        "signals_found": len(signals),
        "trades_executed": len(trades_this_cycle),
        "signals": signals,
        "headlines": headlines,
        "markets": markets,
        "performance": get_performance(),
    }


def get_performance() -> dict:
    """Return current performance metrics."""
    total_trades = state.wins + state.losses + state.pending
    total_wagered = sum(t["amount"] for t in state.trades) or 1

    return {
        "total_trades": total_trades,
        "wins": state.wins,
        "losses": state.losses,
        "pending": state.pending,
        "win_rate": round(state.win_rate, 1),
        "total_pnl": round(state.total_pnl, 2),
        "roi": round(state.roi, 1),
        "total_wagered": round(total_wagered, 2),
        "avg_edge": round(
            sum(t["edge"] for t in state.trades) / max(len(state.trades), 1) * 100, 1
        ),
        "best_trade": round(max((t["pnl"] for t in state.trades), default=0), 2),
        "worst_trade": round(min((t["pnl"] for t in state.trades), default=0), 2),
    }


def get_recent_trades(count: int = 12) -> list[dict]:
    """Return most recent trades."""
    return list(reversed(state.trades[-count:]))


def reset():
    """Reset all state for a fresh demo."""
    global state
    state = MockState()
