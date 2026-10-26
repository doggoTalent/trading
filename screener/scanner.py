"""Single scanner run: universe -> bulk tickers -> OHLCV -> filter -> watchlist"""
from __future__ import annotations

import asyncio
import structlog
from typing import Any

import ccxt.async_support as ccxt
import pandas as pd

from shared.config import ScannerCfg
from shared.watchlist import upsert_from_scan

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------- universe
def select_universe(ex: ccxt.Exchange, cfg: ScannerCfg) -> list[str]:
    """Theoretically valid tickers."""
    bases = {b.upper() for b in cfg.exclude_bases}
    suffixes = tuple(s.upper() for s in cfg.exclude_suffixes)
    out: list[str] = []

    market_type = ex.options.get("defaultType", "spot")

    for m in ex.markets.values():
        if not m.get("active"):
            continue
        if m.get("quote") != "USDT":
            continue
        if market_type == "spot" and not m.get("spot"):
            continue
        if market_type in ("future", "swap") and not m.get("swap") and not m.get("future"):
            continue
            
        base = (m.get("base") or "").upper()
        if not base or base in bases:
            continue
        if suffixes and base.endswith(suffixes):
            continue
        out.append(m["symbol"])
        
    return out


# ---------------------------------------------------------------- features
def compute_features(df: pd.DataFrame, lookback: int) -> dict[str, float] | None:
    """
    df: closed, min lookback+20 lines.
    returns growth_pct & natr_pct or None if data missing.
    """
    if len(df) < lookback + 20:
        return None
    close = df["close"]
    base = close.iloc[-lookback - 1]
    if base <= 0 or close.iloc[-1] <= 0:
        return None
    growth_pct = float((close.iloc[-1] / base - 1.0) * 100.0)

    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - close.shift()).abs(),
            (df["low"] - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    if pd.isna(atr) or close.iloc[-1] <= 0:
        return None
    natr_pct = float(atr / close.iloc[-1] * 100.0)
    return {"growth_pct": growth_pct, "natr_pct": natr_pct}


def passes(features: dict[str, float], cfg: ScannerCfg) -> bool:
    return (
        features["growth_pct"] >= cfg.min_growth_pct
        and features["natr_pct"] >= cfg.min_natr_pct
    )


# ---------------------------------------------------------------- per-symbol
async def _check_symbol(
    ex: ccxt.Exchange,
    sem: asyncio.Semaphore,
    symbol: str,
    cfg: ScannerCfg,
) -> tuple[str, dict[str, float], float] | None:
    """Returns (symbol, features, price) if passed filters or None."""
    async with sem:
        try:
            ohlcv = await ex.fetch_ohlcv(symbol, cfg.scan_tf, limit=cfg.ohlcv_limit)
        except Exception as e:
            log.warning("fetch_ohlcv failed", symbol=symbol, error=str(e))
            return None

    if not ohlcv or len(ohlcv) < cfg.lookback + 20:
        return None

    # Ignoring last bar
    df = pd.DataFrame(
        ohlcv, columns=["ts", "open", "high", "low", "close", "volume"]
    ).iloc[:-1]
    feats = compute_features(df, cfg.lookback)
    if feats is None or not passes(feats, cfg):
        return None

    return symbol, feats, float(df["close"].iloc[-1])


# ---------------------------------------------------------------- entrypoint
async def scan_once(
    ex: ccxt.Exchange,
    conn,
    cfg: ScannerCfg,
    ttl_hours: int,
) -> list[str]:
    """Single run. returns tickers added to watchlist."""
    universe = select_universe(ex, cfg)
    log.info("universe built", total=len(universe))
    if not universe:
        log.error("empty universe — check exchange.markets")
        return []

    # 1. Bulk tickers
    try:
        all_tickers = await ex.fetch_tickers()
    except Exception:
        log.exception("fetch_tickers failed")
        return []

    universe_set = set(universe)
    tickers = {s: t for s, t in all_tickers.items() if s in universe_set}
    log.info("tickers", total=len(all_tickers), in_universe=len(tickers))

    # 2. Volume prefilter
    shortlist = [
        s
        for s in universe
        if (tickers.get(s) or {}).get("quoteVolume", 0) >= cfg.min_quote_volume
    ]
    log.info("shortlist after volume", n=len(shortlist))

    # 3. OHLCV
    sem = asyncio.Semaphore(cfg.concurrency)
    results = await asyncio.gather(
        *(_check_symbol(ex, sem, s, cfg) for s in shortlist),
        return_exceptions=False,
    )

    # 4. Writing to watchlist
    added: list[str] = []
    for r in results:
        if r is None:
            continue
        symbol, feats, price = r
        try:
            await upsert_from_scan(
                conn,
                symbol,
                ttl_hours=ttl_hours,
                growth=feats["growth_pct"],
                natr=feats["natr_pct"],
                price=price,
            )
            added.append(symbol)
            log.info("hit", symbol=symbol, **feats, price=price)
        except Exception:
            log.exception("upsert failed", symbol=symbol)
    return added
