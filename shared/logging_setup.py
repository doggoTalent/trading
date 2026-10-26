"""structlog → JSON (or console) in data/logs/<proc>.jsonl."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog

from .config import LoggingCfg


def setup_logging(name: str, cfg: LoggingCfg) -> None:
    log_dir = Path(os.getenv("LOG_DIR", "data/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{name}.jsonl"

    file_handler = logging.FileHandler(path, encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stderr)
    for h in (file_handler, console_handler):
        h.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, cfg.level))
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if cfg.json_output
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, cfg.level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for noisy in ("ccxt", "asyncio", "urllib3", "websockets", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
