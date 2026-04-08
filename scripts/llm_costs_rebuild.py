"""Rebuild LLM cost summary from logs/llm_costs.csv.

Run:
    .venv\\Scripts\\python.exe scripts\\llm_costs_rebuild.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
import re

from app.services.pipeline import LLM_COSTS_LOG, LLM_COSTS_SUMMARY, InvoicePipelineService


def _request_day(request_id: str | None) -> str:
    if request_id:
        match = re.match(r"^(?P<date>\d{8})_", request_id)
        if match:
            date_raw = match.group("date")
            return f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    return "unknown"


def main() -> int:
    if not LLM_COSTS_LOG.exists():
        print("llm_costs.csv not found.")
        return 1

    total_usd = 0.0
    rows = 0
    by_day: dict[str, dict[str, float | int]] = {}
    by_user: dict[str, dict[str, float | int]] = {}

    with LLM_COSTS_LOG.open("r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                added = float(row.get("total_cost_usd") or 0.0)
                total_usd += added
                rows += 1

                day_key = _request_day(row.get("request_id"))
                day_bucket = by_day.setdefault(day_key, {"rows": 0, "total_usd": 0.0})
                day_bucket["rows"] = int(day_bucket.get("rows") or 0) + 1
                day_bucket["total_usd"] = round(float(day_bucket.get("total_usd") or 0.0) + added, 6)

                user_key = (row.get("user_id") or "unknown").strip() or "unknown"
                user_bucket = by_user.setdefault(user_key, {"rows": 0, "total_usd": 0.0})
                user_bucket["rows"] = int(user_bucket.get("rows") or 0) + 1
                user_bucket["total_usd"] = round(float(user_bucket.get("total_usd") or 0.0) + added, 6)
            except Exception:
                continue

    service = InvoicePipelineService()
    rate = service._get_usd_rub_rate()
    total_rub = round(total_usd * rate, 2) if rate else None

    payload = {
        "total_usd": round(total_usd, 6),
        "total_rub": total_rub,
        "rate": round(rate, 4) if rate else None,
        "rows": rows,
        "by_day": by_day,
        "by_user": by_user,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    LLM_COSTS_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = LLM_COSTS_SUMMARY.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(LLM_COSTS_SUMMARY)

    print(f"Rebuilt summary: rows={rows}, total_usd={payload['total_usd']}, total_rub={payload['total_rub']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
