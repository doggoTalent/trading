from datetime import datetime, timezone
import aiosqlite


async def beat(conn: aiosqlite.Connection, name: str, meta: str = "") -> None:
    await conn.execute(
        "INSERT INTO heartbeat (name, ts, meta) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET ts=excluded.ts, meta=excluded.meta",
        (name, datetime.now(timezone.utc).isoformat(), meta),
    )
    await conn.commit()


async def age_seconds(conn: aiosqlite.Connection, name: str) -> float | None:
    cur = await conn.execute("SELECT ts FROM heartbeat WHERE name=?", (name,))
    row = await cur.fetchone()
    if not row:
        return None
    ts = datetime.fromisoformat(row["ts"])
    return (datetime.now(timezone.utc) - ts).total_seconds()
