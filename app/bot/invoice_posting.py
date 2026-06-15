"""Helpers for posting-readiness checks and review text."""

from __future__ import annotations

from typing import Any

from app.bot.messages import Msg
from app.utils.user_messages import short_request_code

_PRODUCT_KEYS = (
    "product",
    "productid",
    "productguid",
    "productarticle",
    "article",
    "num",
    "supplierproduct",
    "supplierproductid",
    "supplierproductguid",
    "supplierproductarticle",
)


def _normalized_extras(item: dict[str, Any]) -> dict[str, str]:
    raw = item.get("extras") or {}
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        norm_key = str(key or "").strip().lower()
        norm_value = str(value or "").strip()
        if norm_key and norm_value:
            normalized[norm_key] = norm_value
    return normalized


def _has_product_mapping(item: dict[str, Any]) -> bool:
    extras = _normalized_extras(item)
    return any(extras.get(key) for key in _PRODUCT_KEYS)


def is_row_ready(item: dict[str, Any]) -> bool:
    unit = str(item.get("unit_measure") or "").strip()
    qty = item.get("unit_amount") or item.get("supply_quantity")
    has_qty = qty is not None and str(qty).strip() not in {"", "0", "0.0"}
    return _has_product_mapping(item) and bool(unit) and has_qty


def count_posting_rows(items: list[dict[str, Any]]) -> tuple[int, int]:
    ready = 0
    blocked = 0
    for item in items:
        if is_row_ready(item):
            ready += 1
        else:
            blocked += 1
    return ready, blocked


def append_sync_note(base_text: str, note: str) -> str:
    note = note.strip()
    if not note:
        return base_text
    return f"{base_text.rstrip()}\n\n{Msg.INVOICE_SEPARATOR}\n{note}"


def format_sync_note(*, total_rows: int, matched: int, created: int) -> str:
    return Msg.SYNC_NOM_DONE_NOTE.format(
        total_rows=total_rows,
        matched=matched,
        created=created,
    )


def format_posting_review_text(payload: dict[str, Any], *, units: list[str] | None = None) -> str:
    parsed = payload.get("parsed") or {}
    items = list(parsed.get("items") or payload.get("items") or [])
    ready, blocked = count_posting_rows(items)

    lines = [Msg.POSTING_REVIEW_TITLE, ""]
    lines.append(Msg.POSTING_REVIEW_SUMMARY.format(ready=ready, blocked=blocked))
    lines.append("")

    preview = items[:12]
    for index, item in enumerate(preview, start=1):
        status = "🟩" if is_row_ready(item) else "🟥"
        name = str(item.get("name") or Msg.INVOICE_UNKNOWN)
        unit = str(item.get("unit_measure") or "—")
        qty = item.get("unit_amount") or item.get("supply_quantity") or "—"
        lines.append(Msg.POSTING_REVIEW_ROW.format(status=status, index=index, name=name, qty=qty, unit=unit))

    if len(items) > len(preview):
        lines.append(Msg.POSTING_REVIEW_MORE.format(count=len(items) - len(preview)))

    if units:
        lines.append("")
        lines.append(Msg.POSTING_REVIEW_UNITS.format(units=", ".join(units[:20])))

    sync_note = str(payload.get("nomenclature_sync_note") or "").strip()
    if sync_note:
        lines.append("")
        lines.append(Msg.INVOICE_SEPARATOR)
        lines.append(sync_note)

    code = short_request_code(str(payload.get("request_id") or ""))
    if code:
        lines.append("")
        lines.append(Msg.RESP_CODE.format(code=code))

    return "\n".join(lines).strip()
