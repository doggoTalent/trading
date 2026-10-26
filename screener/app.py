"""scanner cycle: adjusting for scan_tf, short DB queries"""
from __future__ import annotations

import asyncio
import structlog
import signal
from datetime import datetime, timezone

from shared import db, exchange, heartbeat
from shared.config import load_config
from shared.logging_setup import setup_logging

from . import scanner

log = structlog.get_logger(__name__)


def next_bar_close(tf: str, now: datetime | None = None) -> datetime:
    """Closest bar closure (UTC)"""
    unit, n = tf[-1], int(tf[:-1])
    minutes = n * {"m": 1, "h": 60, "d": 1440}[unit]
    now = now or datetime.now(timezone.utc)
    epoch_min = int(now.timestamp() // 60)
    next_min = ((epoch_min // minutes) + 1) * minutes
    return datetime.fromtimestamp(next_min * 60, tz=timezone.utc)


async def main() -> None:
    cfg = load_config()
    setup_logging("screener", cfg.logging)
    from shared.config import config_hash
    log.info("screener starting",
             scan_tf=cfg.scanner.scan_tf,
             config_hash=config_hash(cfg))

    ex = exchange.build(cfg.exchange)
    await ex.load_markets()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        while not stop.is_set():
            target = next_bar_close(cfg.scanner.scan_tf)
            sleep_s = (target - datetime.now(timezone.utc)).total_seconds()
            log.info("next scan", at=target.isoformat(), sleep_s=int(sleep_s))

            try:
                await asyncio.wait_for(stop.wait(), timeout=max(sleep_s, 1.0))
                break
            except asyncio.TimeoutError:
                pass

            # --- single scanner run ---
            conn = await db.connect()
            try:
                added = await scanner.scan_once(
                    ex, conn, cfg.scanner, cfg.watchlist.ttl_hours
                )
                await heartbeat.beat(conn, "screener", meta=f"added={len(added)}")
                log.info("scan done", added=len(added))
            except Exception:
                log.exception("scan failed")
                # waiting for the next run
            finally:
                await conn.close()
    finally:
        await ex.close()
        log.info("screener stopped")
