"""Manual scan_once run. launch: APP_ENV=dev python3 scripts/probe_scan.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import load_config
from shared.db import connect
from shared.exchange import build
from screener.scanner import scan_once

async def main() -> int:
    cfg = load_config()
    ex = build(cfg.exchange)
    await ex.load_markets()
    conn = await connect()
    try:
        added = await scan_once(ex, conn, cfg.scanner, cfg.watchlist.ttl_hours)
        print(f"\n=== ADDED {len(added)} symbols ===")
        for s in added:
            print(" ", s)

        cur = await conn.execute(
            "SELECT symbol, scan_growth, scan_natr, scan_price "
            "FROM watchlist WHERE status='waiting' ORDER BY scan_growth DESC"
        )
        rows = await cur.fetchall()
        print(f"\n=== WATCHLIST ({len(rows)} waiting) ===")
        for r in rows:
            print(
                f"  {r['symbol']:<18} "
                f"growth={r['scan_growth']:6.2f}% "
                f"natr={r['scan_natr']:5.2f}% "
                f"price={r['scan_price']}"
            )
    finally:
        await ex.close()
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
