"""
Portfolio — paper-trading ledger for the market-data bot.

Tracks a cash balance, open positions (shares of a YES/NO token bought at an
average price), realized P&L from closed positions, and mark-to-market
unrealized P&L against live prices. Persisted in the same SQLite file the rest
of the pipeline uses (trades.db) so the CLI can report on it across runs.

A "position" is a directional bet: BUY <shares> of the <side> token at
<avg_price>. On Polymarket every share pays out $1 if that side resolves true
and $0 otherwise, so cost = shares * price and max payout = shares.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config

DB_PATH = Path(__file__).parent / "trades.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_portfolio_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash REAL NOT NULL,
            starting_cash REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            token_id TEXT,
            question TEXT NOT NULL,
            side TEXT NOT NULL,          -- YES / NO
            shares REAL NOT NULL,        -- outstanding shares (0 once closed)
            avg_price REAL NOT NULL,     -- average entry price
            cost_basis REAL NOT NULL,    -- shares * avg_price still at risk
            strategy TEXT,
            status TEXT NOT NULL DEFAULT 'open',  -- open / closed
            realized_pnl REAL NOT NULL DEFAULT 0,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            UNIQUE(market_id, token_id, side, status)
        );

        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,        -- BUY / SELL / RESOLVE
            market_id TEXT,
            question TEXT,
            side TEXT,
            shares REAL,
            price REAL,
            cash_delta REAL,
            realized_pnl REAL,
            strategy TEXT,
            note TEXT
        );
    """)
    conn.commit()
    # Seed the account on first use.
    row = conn.execute("SELECT id FROM account WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO account (id, cash, starting_cash, created_at) VALUES (1, ?, ?, ?)",
            (config.STARTING_BANKROLL_USD, config.STARTING_BANKROLL_USD, _now()),
        )
        conn.commit()
    conn.close()


@dataclass
class Position:
    id: int
    market_id: str
    token_id: str | None
    question: str
    side: str
    shares: float
    avg_price: float
    cost_basis: float
    strategy: str | None
    status: str

    def unrealized_pnl(self, current_price: float) -> float:
        """Mark-to-market: what the shares are worth now minus what's at risk."""
        return self.shares * current_price - self.cost_basis


def get_cash() -> float:
    conn = _conn()
    row = conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()
    conn.close()
    return row["cash"] if row else 0.0


def get_open_positions() -> list[Position]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status = 'open' AND shares > 0 ORDER BY opened_at"
    ).fetchall()
    conn.close()
    return [
        Position(
            id=r["id"], market_id=r["market_id"], token_id=r["token_id"],
            question=r["question"], side=r["side"], shares=r["shares"],
            avg_price=r["avg_price"], cost_basis=r["cost_basis"],
            strategy=r["strategy"], status=r["status"],
        )
        for r in rows
    ]


def find_open_position(market_id: str, side: str) -> Position | None:
    for p in get_open_positions():
        if p.market_id == market_id and p.side == side:
            return p
    return None


def total_exposure() -> float:
    """Dollars currently at risk in open positions."""
    return sum(p.cost_basis for p in get_open_positions())


def buy(market_id: str, token_id: str | None, question: str, side: str,
        price: float, usd: float, strategy: str = "") -> Position | None:
    """
    Buy `usd` worth of the `side` token at `price`. Averages into an existing
    open position on the same side. Returns the resulting Position, or None if
    there isn't enough cash.
    """
    if price <= 0 or price >= 1 or usd <= 0:
        return None
    conn = _conn()
    cash = conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"]
    if usd > cash + 1e-9:
        conn.close()
        return None

    shares = usd / price
    existing = conn.execute(
        "SELECT * FROM positions WHERE market_id=? AND side=? AND status='open'",
        (market_id, side),
    ).fetchone()

    if existing:
        new_shares = existing["shares"] + shares
        new_cost = existing["cost_basis"] + usd
        new_avg = new_cost / new_shares
        conn.execute(
            "UPDATE positions SET shares=?, avg_price=?, cost_basis=? WHERE id=?",
            (new_shares, new_avg, new_cost, existing["id"]),
        )
        pos_id = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO positions
               (market_id, token_id, question, side, shares, avg_price,
                cost_basis, strategy, status, opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (market_id, token_id, question, side, shares, price, usd, strategy, _now()),
        )
        pos_id = cur.lastrowid

    conn.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (usd,))
    conn.execute(
        """INSERT INTO ledger (ts, action, market_id, question, side, shares,
           price, cash_delta, realized_pnl, strategy, note)
           VALUES (?, 'BUY', ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (_now(), market_id, question, side, shares, price, -usd, strategy, ""),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM positions WHERE id=?", (pos_id,)).fetchone()
    conn.close()
    return Position(
        id=row["id"], market_id=row["market_id"], token_id=row["token_id"],
        question=row["question"], side=row["side"], shares=row["shares"],
        avg_price=row["avg_price"], cost_basis=row["cost_basis"],
        strategy=row["strategy"], status=row["status"],
    )


def sell(position: Position, price: float, note: str = "") -> float:
    """
    Close a position at `price` (sell all shares back to the book). Credits
    cash and books realized P&L. Returns realized P&L.
    """
    proceeds = position.shares * price
    realized = proceeds - position.cost_basis
    conn = _conn()
    conn.execute(
        """UPDATE positions
           SET shares=0, cost_basis=0, status='closed',
               realized_pnl=realized_pnl + ?, closed_at=?
           WHERE id=?""",
        (realized, _now(), position.id),
    )
    conn.execute("UPDATE account SET cash = cash + ? WHERE id = 1", (proceeds,))
    conn.execute(
        """INSERT INTO ledger (ts, action, market_id, question, side, shares,
           price, cash_delta, realized_pnl, strategy, note)
           VALUES (?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), position.market_id, position.question, position.side,
         position.shares, price, proceeds, realized, position.strategy, note),
    )
    conn.commit()
    conn.close()
    return realized


def resolve(position: Position, won: bool) -> float:
    """
    Settle a position at market resolution: winning shares pay $1 each, losing
    shares pay $0. Returns realized P&L.
    """
    return sell(position, price=1.0 if won else 0.0, note="resolved")


def summary(price_lookup: dict[str, float] | None = None) -> dict:
    """
    Portfolio snapshot. `price_lookup` maps market_id -> current YES price so
    open positions can be marked to market.
    """
    price_lookup = price_lookup or {}
    cash = get_cash()
    conn = _conn()
    starting = conn.execute("SELECT starting_cash FROM account WHERE id=1").fetchone()["starting_cash"]
    realized = conn.execute(
        "SELECT COALESCE(SUM(realized_pnl), 0) AS r FROM ledger WHERE action IN ('SELL','RESOLVE')"
    ).fetchone()["r"]
    conn.close()

    open_positions = get_open_positions()
    unrealized = 0.0
    position_value = 0.0
    for p in open_positions:
        yes_price = price_lookup.get(p.market_id)
        if yes_price is None:
            mark = p.avg_price  # no live price → hold at cost
        else:
            mark = yes_price if p.side == "YES" else (1.0 - yes_price)
        position_value += p.shares * mark
        unrealized += p.unrealized_pnl(mark)

    equity = cash + position_value
    return {
        "cash": cash,
        "starting_cash": starting,
        "open_positions": len(open_positions),
        "exposure": sum(p.cost_basis for p in open_positions),
        "position_value": position_value,
        "equity": equity,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "total_pnl": equity - starting,
        "return_pct": (equity - starting) / starting * 100 if starting else 0.0,
    }


def reset(bankroll: float | None = None):
    """Wipe all bot positions/ledger and reset cash. For paper trading resets."""
    conn = _conn()
    conn.execute("DELETE FROM positions")
    conn.execute("DELETE FROM ledger")
    start = bankroll if bankroll is not None else config.STARTING_BANKROLL_USD
    conn.execute(
        "INSERT OR REPLACE INTO account (id, cash, starting_cash, created_at) VALUES (1, ?, ?, ?)",
        (start, start, _now()),
    )
    conn.commit()
    conn.close()


init_portfolio_db()
