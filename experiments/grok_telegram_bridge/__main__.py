"""Entry: python -m experiments.grok_telegram_bridge"""
from __future__ import annotations

import asyncio

from experiments.grok_telegram_bridge.bot import main

if __name__ == "__main__":
    asyncio.run(main())
