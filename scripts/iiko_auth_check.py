"""Check iiko API authorization with given credentials."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.iiko.server_client import IikoServerClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="iiko login")
    parser.add_argument("--password", required=True, help="iiko password")
    return parser


async def _run(login: str, password: str) -> int:
    client = IikoServerClient()
    try:
        await client.verify_credentials(login, password)
    except Exception as exc:  # noqa: BLE001
        print(f"IIKO_AUTH_FAIL: {exc}")
        return 1
    print("IIKO_AUTH_OK")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_run(args.login, args.password))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
