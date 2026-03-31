from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "trades.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            market_question TEXT NOT NULL,
            claude_score REAL NOT NULL,
            market_price REAL NOT NULL,
            edge REAL NOT NULL,
            side TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            order_id TEXT,
            status TEXT NOT NULL DEFAULT 'dry_run',
            reasoning TEXT,
            headlines TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL REFERENCES trades(id),
            resolved_at TEXT,
            result TEXT,
            pnl REAL,
            UNIQUE(trade_id)
        );

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            markets_scanned INTEGER DEFAULT 0,
            signals_found INTEGER DEFAULT 0,
            trades_placed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        );
    """)
    conn.close()


def log_trade(
    market_id: str,
    market_question: str,
    claude_score: float,
    market_price: float,
    edge: float,
    side: str,
    amount_usd: float,
    order_id: str | None = None,
    status: str = "dry_run",
    reasoning: str = "",
    headlines: str = "",
) -> int:
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO trades
           (market_id, market_question, claude_score, market_price, edge,
            side, amount_usd, order_id, status, reasoning, headlines)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (market_id, market_question, claude_score, market_price, edge,
         side, amount_usd, order_id, status, reasoning, headlines),
    )
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def log_run_start() -> int:
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO pipeline_runs (started_at) VALUES (?)", (now,)
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_run_end(run_id: int, markets_scanned: int, signals_found: int, trades_placed: int, status: str = "completed"):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE pipeline_runs
           SET finished_at=?, markets_scanned=?, signals_found=?, trades_placed=?, status=?
           WHERE id=?""",
        (now, markets_scanned, signals_found, trades_placed, status, run_id),
    )
    conn.commit()
    conn.close()


def get_daily_pnl() -> float:
    conn = _conn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        """SELECT COALESCE(SUM(
               CASE WHEN status IN ('filled','executed') THEN -amount_usd ELSE 0 END
           ), 0) as spent
           FROM trades WHERE created_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()
    conn.close()
    return row["spent"]


def get_recent_trades(limit: int = 20) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_stats() -> dict:
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as c FROM trades GROUP BY status"
    ).fetchall()
    conn.close()
    return {
        "total_trades": total,
        "by_status": {r["status"]: r["c"] for r in by_status},
    }


init_db()
