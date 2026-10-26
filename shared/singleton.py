"""flock: forbids second exemplar"""
from __future__ import annotations

import fcntl
import os
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def single_instance(name: str, lock_dir: Path = Path("data")):
    lock_dir.mkdir(parents=True, exist_ok=True)
    f = open(lock_dir / f"{name}.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(f"another '{name}' is already running (lock: {f.name})")
    try:
        f.write(str(os.getpid()))
        f.flush()
        yield
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()
