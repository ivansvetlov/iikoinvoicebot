"""Append-only log of every OpenAI API call (one CSV row per HTTP request)."""

from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_COSTS_LOG = PROJECT_ROOT / "logs" / "llm_costs.csv"
LLM_COSTS_SUMMARY = PROJECT_ROOT / "logs" / "llm_costs_summary.json"

CSV_HEADER = (
    "user_id,request_id,call_kind,model,input_tokens,output_tokens,"
    "input_cost_usd,output_cost_usd,total_cost_usd"
)
LEGACY_CSV_HEADER = (
    "user_id,request_id,model,input_tokens,output_tokens,"
    "input_cost_usd,output_cost_usd,total_cost_usd"
)

# OpenAI public pricing (USD per 1M tokens) — extend as new models ship.
MODEL_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.30, "output": 1.20},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}

_usage_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_usage_user_id", default=None)
_usage_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_usage_request_id", default=None)


def set_usage_context(*, user_id: str | None, request_id: str | None) -> tuple[contextvars.Token, contextvars.Token]:
    """Bind user/request for nested OpenAI calls (race, retries, flow LLM)."""
    return (
        _usage_user_id.set(user_id),
        _usage_request_id.set(request_id),
    )


def reset_usage_context(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    user_token, request_token = tokens
    _usage_user_id.reset(user_token)
    _usage_request_id.reset(request_token)


def estimate_cost(usage: dict[str, Any], model: str) -> dict[str, Any] | None:
    if not usage:
        return None
    pricing = MODEL_PRICING_USD_PER_1M.get(model)
    if not pricing:
        for key, value in MODEL_PRICING_USD_PER_1M.items():
            if model.startswith(key):
                pricing = value
                break
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    if not pricing:
        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "total_cost_usd": 0.0,
        }
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6),
    }


def log_openai_response(
    response_data: dict[str, Any],
    *,
    model: str,
    call_kind: str,
    user_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Record one OpenAI /v1/responses call when usage is present."""
    usage = response_data.get("usage") if isinstance(response_data, dict) else None
    if not isinstance(usage, dict) or not usage:
        return
    cost = estimate_cost(usage, model)
    if not cost:
        return
    append_cost_row(
        user_id=user_id or _usage_user_id.get() or "unknown",
        request_id=request_id or _usage_request_id.get() or "unknown",
        call_kind=call_kind,
        cost=cost,
    )


def append_cost_row(
    *,
    user_id: str | None,
    request_id: str | None,
    cost: dict[str, Any],
    call_kind: str = "openai",
) -> None:
    safe_user = user_id or _usage_user_id.get() or "unknown"
    safe_request = request_id or _usage_request_id.get() or "unknown"
    row = [
        safe_user,
        safe_request,
        call_kind,
        str(cost.get("model") or ""),
        str(cost.get("input_tokens") or 0),
        str(cost.get("output_tokens") or 0),
        str(cost.get("input_cost_usd") or 0),
        str(cost.get("output_cost_usd") or 0),
        str(cost.get("total_cost_usd") or 0),
    ]
    try:
        LLM_COSTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        need_header = True
        if LLM_COSTS_LOG.exists():
            with LLM_COSTS_LOG.open("r", encoding="utf-8", errors="replace") as handle:
                first = handle.readline().strip()
            need_header = not first
        with LLM_COSTS_LOG.open("a", encoding="utf-8") as handle:
            if need_header:
                handle.write(CSV_HEADER + "\n")
            handle.write(",".join(row) + "\n")
        update_cost_summary(user_id=safe_user, request_id=safe_request, cost=cost)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to append LLM usage row", extra={"request_id": safe_request})


def _request_day(request_id: str | None) -> str:
    if request_id:
        match = re.match(r"^(?P<date>\d{8})_", request_id)
        if match:
            date_raw = match.group("date")
            return f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    return datetime.now().date().isoformat()


def update_cost_summary(*, user_id: str, request_id: str, cost: dict[str, Any]) -> None:
    try:
        LLM_COSTS_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        summary: dict[str, Any] = {}
        if LLM_COSTS_SUMMARY.exists():
            try:
                summary = json.loads(LLM_COSTS_SUMMARY.read_text(encoding="utf-8"))
            except Exception:
                summary = {}

        total_usd = float(summary.get("total_usd") or 0.0)
        rows = int(summary.get("rows") or 0)
        added = float(cost.get("total_cost_usd") or 0.0)
        total_usd += added
        rows += 1

        by_day = dict(summary.get("by_day") or {})
        day_key = _request_day(request_id)
        day_bucket = dict(by_day.get(day_key) or {})
        day_bucket["rows"] = int(day_bucket.get("rows") or 0) + 1
        day_bucket["total_usd"] = round(float(day_bucket.get("total_usd") or 0.0) + added, 6)
        by_day[day_key] = day_bucket

        by_user = dict(summary.get("by_user") or {})
        user_bucket = dict(by_user.get(user_id) or {})
        user_bucket["rows"] = int(user_bucket.get("rows") or 0) + 1
        user_bucket["total_usd"] = round(float(user_bucket.get("total_usd") or 0.0) + added, 6)
        by_user[user_id] = user_bucket

        payload = {
            "total_usd": round(total_usd, 6),
            "total_rub": summary.get("total_rub"),
            "rate": summary.get("rate"),
            "rows": rows,
            "by_day": by_day,
            "by_user": by_user,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        tmp_path = LLM_COSTS_SUMMARY.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(LLM_COSTS_SUMMARY)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update LLM cost summary", extra={"request_id": request_id})