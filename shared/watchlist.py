"""CRUD watchlist."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import aiosqlite

_UPSERT_SQL = """
INSERT INTO watchlist
    (symbol, added_at, expires_at, status, status_changed_at,
     scan_growth, scan_natr, scan_price, meta)
VALUES (?, ?, ?, 'waiting', ?, ?, ?, ?, NULL)
ON CONFLICT(symbol) DO UPDATE SET
    expires_at        = excluded.expires_at,
    status            = 'waiting',
    status_changed_at = excluded.status_changed_at,
    scan_growth       = excluded.scan_growth,
    scan_natr         = excluded.scan_natr,
    scan_price        = excluded.scan_price
WHERE watchlist.status IN ('expired', 'closed', 'rejected')
"""


async def upsert_from_scan(
    conn: aiosqlite.Connection,
    symbol: str,
    *,
    ttl_hours: int,
    growth: float,
    natr: float,
    price: float,
) -> None:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)
    await conn.execute(
        _UPSERT_SQL,
        (symbol, now.isoformat(), expires.isoformat(), now.isoformat(),
         growth, natr, price),
    )
    await conn.commit()


async def sweep_expired(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        "UPDATE watchlist SET status='expired', status_changed_at=? "
        "WHERE status='waiting' AND expires_at <= ?",
        (datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()),
    )
    await conn.commit()
    return cur.rowcount or 0
