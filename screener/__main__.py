"""Entry point: python -m screener."""
import asyncio
from shared.singleton import single_instance
from .app import main

if __name__ == "__main__":
    with single_instance("screener"):
        asyncio.run(main())
