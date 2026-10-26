"""Loading overwriting and validating config."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
VALID_TFS = {"1m", "5m", "15m", "1h", "4h", "1d"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExchangeCfg(_Strict):
    id: str = "binance"
    market_type: str = "spot"
    rate_limit: bool = True
    timeout_ms: int = Field(15_000, ge=1_000, le=60_000)


class ScannerCfg(_Strict):
    scan_tf: str = "4h"
    lookback: int = Field(6, ge=1, le=200)
    min_growth_pct: float = Field(5.0, ge=-100.0, le=1000.0)
    min_natr_pct: float = Field(2.0, ge=0.0, le=100.0)
    min_quote_volume: float = Field(5_000_000, ge=0.0)
    concurrency: int = Field(10, ge=1, le=50)
    ohlcv_limit: int = Field(200, ge=50, le=1000)
    exclude_bases: list[str] = []
    exclude_suffixes: list[str] = []

    @field_validator("scan_tf")
    @classmethod
    def _tf(cls, v: str) -> str:
        if v not in VALID_TFS:
            raise ValueError(f"scan_tf must be in {sorted(VALID_TFS)}")
        return v


class WatchlistCfg(_Strict):
    ttl_hours: int = Field(24, ge=1, le=168)
    max_size: int = Field(30, ge=1, le=500)
    max_price_drift_pct: float = Field(8.0, ge=0.0, le=50.0)


class ExecutorCfg(_Strict):
    entry_tf: str = "15m"
    max_positions: int = Field(5, ge=1, le=100)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=10.0)
    max_daily_loss_pct: float = Field(3.0, gt=0.0, le=100.0)
    order_timeout_sec: int = Field(30, ge=1, le=600)
    ohlcv_limit: int = Field(200, ge=50, le=1000)

    @field_validator("entry_tf")
    @classmethod
    def _tf(cls, v: str) -> str:
        if v not in VALID_TFS:
            raise ValueError(f"entry_tf must be in {sorted(VALID_TFS)}")
        return v


class RiskCfg(_Strict):
    max_exposure_per_symbol_pct: float = Field(2.0, gt=0.0, le=100.0)
    kill_switch_drawdown_pct: float = Field(10.0, gt=0.0, le=100.0)


class LoggingCfg(_Strict):
    level: str = "INFO"
    json_output: bool = True

    @field_validator("level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("logging.level must be DEBUG|INFO|WARNING|ERROR")
        return v


class StrategyCfg(_Strict):
    name: str = "placeholder"
    params: dict = {}


class AppCfg(_Strict):
    exchange: ExchangeCfg
    scanner: ScannerCfg
    watchlist: WatchlistCfg
    executor: ExecutorCfg
    risk: RiskCfg
    logging: LoggingCfg
    strategy: StrategyCfg


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _tf_minutes(tf: str) -> int:
    unit, n = tf[-1], int(tf[:-1])
    return n * {"m": 1, "h": 60, "d": 1440}[unit]


def validate_invariants(cfg: AppCfg) -> None:
    if _tf_minutes(cfg.executor.entry_tf) >= _tf_minutes(cfg.scanner.scan_tf):
        raise ValueError(
            f"entry_tf ({cfg.executor.entry_tf}) must be < "
            f"scan_tf ({cfg.scanner.scan_tf})"
        )
    if cfg.watchlist.max_size < cfg.executor.max_positions:
        raise ValueError("watchlist.max_size must be >= executor.max_positions")
    if cfg.scanner.concurrency > 20:
        raise ValueError("scanner.concurrency > 20 — risk rate limit")


def load_config(env: str | None = None) -> AppCfg:
    env = env or os.getenv("APP_ENV", "dev")
    base_path = CONFIG_DIR / "base.yml"
    if not base_path.exists():
        raise FileNotFoundError(f"config file missing: {base_path}")
    base = yaml.safe_load(base_path.read_text()) or {}
    over_path = CONFIG_DIR / f"{env}.yml"
    over = yaml.safe_load(over_path.read_text()) if over_path.exists() else {}
    cfg = AppCfg(**_deep_merge(base, over or {}))
    validate_invariants(cfg)
    return cfg


def config_hash(cfg: AppCfg) -> str:
    raw = json.dumps(cfg.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
