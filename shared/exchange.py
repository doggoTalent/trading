"""ccxt factory."""
from __future__ import annotations
import ccxt.async_support as ccxt
from .config import ExchangeCfg


def build(cfg: ExchangeCfg) -> ccxt.Exchange:
    cls = getattr(ccxt, cfg.id)
    return cls({
        "enableRateLimit": cfg.rate_limit,
        "timeout": cfg.timeout_ms,
        "apiKey": None,          # screener - API keys not required
        "secret": None,
        "options": {"defaultType": cfg.market_type},
    })
