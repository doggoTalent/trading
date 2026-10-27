"""Parquet local OHLCV cache. key: {exchange}_{symbol}_{tf}."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
import pandas as pd

def _cache_dir() -> Path:
    d = Path(os.getenv("CACHE_DIR", "data/cache"))
    d.mkdir(parents=True, exist_ok=True)
    return d

def _safe(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").replace(" ", "_")

def _path(exchange_id: str, symbol: str, tf: str) -> Path:
    return _cache_dir() / f"{exchange_id}_{_safe(symbol)}_{tf}.parquet"

def load(exchange_id: str, symbol: str, tf: str) -> pd.DataFrame | None:
    p = _path(exchange_id, symbol, tf)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df["ts"] = df["ts"].astype("int64")
        return df
    except Exception:
        return None

def save(exchange_id: str, symbol: str, tf: str, df: pd.DataFrame, max_rows: int = 2000) -> None:
    if df.empty:
        return
    df = df.drop_duplicates("ts", keep="last").sort_values("ts").tail(max_rows)
    target = _path(exchange_id, symbol, tf)
    
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp_", suffix=".parquet")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

def clear(exchange_id: str | None = None, symbol: str | None = None) -> int:
    n = 0
    for f in _cache_dir().glob("*.parquet"):
        if exchange_id and not f.name.startswith(f"{exchange_id}_"): continue
        if symbol and _safe(symbol) not in f.name: continue
        f.unlink()
        n += 1
    return n
