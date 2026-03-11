"""Печать сводки метрик обработки (ошибки/длительность)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.observability import summarize_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Show metrics summary from logs/metrics.jsonl")
    parser.add_argument("--minutes", type=int, default=60, help="Window in minutes (default: 60)")
    args = parser.parse_args()

    summary = summarize_metrics(minutes=args.minutes)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
