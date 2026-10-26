"""SQLite: scheme and connection"""
from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS watchlist (
    symbol             TEXT PRIMARY KEY,
    added_at           TEXT NOT NULL,
    expires_at         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'waiting',
    status_changed_at  TEXT NOT NULL,
    scan_growth        REAL,
    scan_natr          REAL,
    scan_price         REAL,
    meta               TEXT
);
CREATE INDEX IF NOT EXISTS idx_watchlist_status
    ON watchlist (status, expires_at);

CREATE TABLE IF NOT EXISTS trades (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol             TEXT NOT NULL,
    side               TEXT NOT NULL,
    qty                REAL NOT NULL,
    entry_price        REAL NOT NULL,
    exit_price         REAL,
    stop_price         REAL,
    status             TEXT NOT NULL,
    client_order_id    TEXT NOT NULL UNIQUE,
    config_hash        TEXT NOT NULL,
    opened_at          TEXT NOT NULL,
    closed_at          TEXT,
    pnl_quote          REAL,
    meta               TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_open ON trades (symbol, status);

CREATE TABLE IF NOT EXISTS heartbeat (
    name   TEXT PRIMARY KEY,
    ts     TEXT NOT NULL,
    meta   TEXT
);
"""


def db_path() -> Path:
    p = Path(os.getenv("DB_PATH", "data/watchlist.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path())
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.executescript(SCHEMA)
    await conn.commit()
    return conn
