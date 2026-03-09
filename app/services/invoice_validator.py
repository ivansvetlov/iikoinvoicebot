"""Правила проверки, что документ похож на накладную."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.schemas import InvoiceItem, InvoiceParseResult

KEYWORD_TOKENS = [
    "наклад",
    "упд",
    "торг-12",
    "товарная наклад",
    "товарно-транспорт",
    "товарно транспорт",
    "счет",
    "счёт",
    "invoice",
    "supplier",
    "vendor",
    "поставщик",
    "получатель",
    "итого",
    "сумма",
    "total",
    "amount",
]

DOC_TYPE_ALIASES = {
    "upd": "UPD",
    "упд": "UPD",
    "torg-12": "TORG-12",
    "торг-12": "TORG-12",
    "ttn": "TTN",
    "товарно-транспортная накладная": "TTN",
    "товарно транспортная накладная": "TTN",
    "invoice": "INVOICE",
}


def _normalize_doc_type(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.strip().lower()
    return DOC_TYPE_ALIASES.get(lowered, lowered)


def _has_invoice_keyword(raw_text: str) -> bool:
    text = (raw_text or "").lower()
    return any(token in text for token in KEYWORD_TOKENS)


def is_likely_invoice(
    items: list[InvoiceItem],
    raw_text: str,
    parsed: InvoiceParseResult,
    source_type: str,
    llm_data: dict[str, Any] | None = None,
) -> bool:
    if not items:
        return False

    llm_data = llm_data or {}
    doc_type = _normalize_doc_type(str(llm_data.get("document_type") or ""))
    has_llm_keyword = llm_data.get("has_invoice_keyword")
    if has_llm_keyword is False:
        return False
    if doc_type in {"UPD", "TORG-12", "TTN", "INVOICE"}:
        return True

    has_keyword = _has_invoice_keyword(raw_text)
    numeric_rows = 0
    for item in items:
        if item.unit_amount is not None or item.unit_price is not None or item.total_cost is not None:
            numeric_rows += 1

    has_invoice_number = bool(parsed.invoice_number and re.search(r"\d", str(parsed.invoice_number)))
    has_vendor = bool(parsed.vendor_name and str(parsed.vendor_name).strip())
    has_total = parsed.total_amount is not None and Decimal(str(parsed.total_amount)) > 0
    has_meta = has_invoice_number or has_vendor or has_total or bool(parsed.invoice_date)

    has_money = False
    for item in items:
        if (item.unit_price and Decimal(str(item.unit_price)) > 0) or (
            item.total_cost and Decimal(str(item.total_cost)) > 0
        ):
            has_money = True
            break

    if has_keyword and numeric_rows >= 1:
        return True
    if has_meta and numeric_rows >= 1 and len(items) >= 2:
        return True
    if source_type != "image" and numeric_rows >= 3 and len(items) >= 3:
        return True
    if source_type == "image" and has_money and len(items) >= 2:
        return True
    return False
