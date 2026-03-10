"""Rebuild LLM cost summary from logs/llm_costs.csv.

Run:
    .venv\Scripts\python.exe scripts\llm_costs_rebuild.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from app.services.pipeline import LLM_COSTS_LOG, LLM_COSTS_SUMMARY, InvoicePipelineService


def main() -> int:
    if not LLM_COSTS_LOG.exists():
        print("llm_costs.csv not found.")
        return 1

    total_usd = 0.0
    rows = 0

    with LLM_COSTS_LOG.open("r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                total_usd += float(row.get("total_cost_usd") or 0.0)
                rows += 1
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
