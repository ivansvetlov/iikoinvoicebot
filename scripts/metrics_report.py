"""Печатает сводку по `logs/metrics.jsonl`.

Запуск:
    .venv\\Scripts\\python.exe scripts\\metrics_report.py --hours 24
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.observability import METRICS_LOG


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * p))))
    return ordered[index]


def _load_rows(path: Path, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            ts = _parse_ts(payload.get("ts"))
            if cutoff and ts and ts < cutoff:
                continue
            rows.append(payload)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Show simple metrics summary from logs/metrics.jsonl")
    parser.add_argument("--hours", type=int, default=24, help="Окно анализа в часах (по умолчанию 24).")
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(hours=max(1, args.hours))
    rows = _load_rows(METRICS_LOG, cutoff)
    if not rows:
        print("No metrics rows found for selected time window.")
        return 0

    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "durations": [], "errors": 0})
    for row in rows:
        event = str(row.get("event") or "unknown")
        status = str(row.get("status") or "n/a")
        key = (event, status)
        grouped[key]["count"] += 1
        duration = row.get("duration_ms")
        try:
            grouped[key]["durations"].append(float(duration))
        except Exception:
            pass
        if status == "error" or int(row.get("status_code") or 0) >= 500:
            grouped[key]["errors"] += 1

    print(f"Metrics window: last {args.hours}h")
    print(f"Rows: {len(rows)}")
    print("---")
    for (event, status), data in sorted(grouped.items(), key=lambda item: item[0]):
        durations = data["durations"]
        p50 = round(_percentile(durations, 0.50), 2) if durations else 0.0
        p95 = round(_percentile(durations, 0.95), 2) if durations else 0.0
        print(
            f"{event:20} status={status:8} count={data['count']:5} "
            f"errors={data['errors']:4} p50_ms={p50:8} p95_ms={p95:8}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
