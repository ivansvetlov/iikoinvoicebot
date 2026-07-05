"""Quick check: iiko API auth for credential pairs (uses .env IIKO_API_BASE_URL)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.iiko.server_client import IikoServerClient

PAIRS = [
    ("admin", "YKKXA2Cf"),
    ("user", "user#test"),
]


async def main() -> int:
    client = IikoServerClient()
    ok = 0
    for login, password in PAIRS:
        try:
            await client.verify_credentials(login, password)
            print(f"OK   {login}")
            ok += 1
        except Exception as exc:
            print(f"FAIL {login}: {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
