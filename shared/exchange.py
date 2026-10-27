"""ccxt factory."""
from __future__ import annotations

import time
import logging
import ccxt.async_support as ccxt
import pandas as pd

from .config import ExchangeCfg
from . import cache

log = logging.getLogger(__name__)
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def build(cfg: ExchangeCfg) -> ccxt.Exchange:
    cls = getattr(ccxt, cfg.id)
    return cls({
        "enableRateLimit": cfg.rate_limit,
        "timeout": cfg.timeout_ms,
        "apiKey": None,          # screener - API keys not required
        "secret": None,
        "options": {"defaultType": cfg.market_type},
    })

async def fetch_ohlcv_cached(ex, symbol: str, tf: str, limit: int) -> pd.DataFrame:
    ex_id = ex.id
    cached = cache.load(ex_id, symbol, tf)

    # 1. No cache or little data
    if cached is None or cached.empty:
        ohlcv = await ex.fetch_ohlcv(symbol, tf, limit=limit)
        if not ohlcv: return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(ohlcv, columns=COLUMNS)
        df["ts"] = df["ts"].astype("int64")
        cache.save(ex_id, symbol, tf, df, max_rows=max(limit * 4, 1000))
        return df

    # 2. Calculating time from last bar
    last_ts = int(cached["ts"].iloc[-1])
    tf_ms = ex.parse_timeframe(tf) * 1000
    now_ms = int(time.time() * 1000)
    
    # Processing large data gaps
    gap_ms = now_ms - last_ts
    if gap_ms > (limit * tf_ms):
        log.info("cache gap too large, full refresh", symbol=symbol, tf=tf)
        ohlcv = await ex.fetch_ohlcv(symbol, tf, limit=limit)
        if not ohlcv: return cached
        df = pd.DataFrame(ohlcv, columns=COLUMNS)
        df["ts"] = df["ts"].astype("int64")
        cache.save(ex_id, symbol, tf, df, max_rows=max(limit * 4, 1000))
        return df

    # 3. Delta-download (only new 1-2 bars)
    try:
        new = await ex.fetch_ohlcv(symbol, tf, since=last_ts)
        if new:
            new_df = pd.DataFrame(new, columns=COLUMNS)
            new_df["ts"] = new_df["ts"].astype("int64")
            merged = pd.concat([cached, new_df], ignore_index=True)
            merged = merged.drop_duplicates("ts", keep="last").sort_values("ts")
            cache.save(ex_id, symbol, tf, merged, max_rows=max(limit * 4, 1000))
            return merged
    except Exception as e:
        log.warning("delta fetch failed", symbol=symbol, error=str(e))

    return cached
