"""Правила проверки, что документ похож на накладную."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas import InvoiceItem, InvoiceParseResult

KEYWORD_TOKENS = [
    "наклад",
    "упд",
    "торг-12",
    "форма торг-12",
    "форма 1-т",
    "форма n 1-т",
    "1-т",
    "товарная наклад",
    "товарно-транспортная накладная",
    "товарно-транспорт",
    "товарно транспорт",
    "универсальный передаточный документ",
    "счет",
    "счёт",
    "счет-фактура",
    "счёт-фактура",
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

RECEIPT_KEYWORD_TOKENS = [
    "чек",
    "кассовый чек",
    "товарный чек",
    "ккт",
    "фн",
    "фд",
    "рн ккт",
    "смена",
    "сдача",
]

DOC_TYPE_ALIASES = {
    "upd": "UPD",
    "упд": "UPD",
    "torg-12": "TORG-12",
    "форма торг-12": "TORG-12",
    "торг-12": "TORG-12",
    "ttn": "TTN",
    "1-т": "TTN",
    "форма 1-т": "TTN",
    "форма n 1-т": "TTN",
    "форма 1 т": "TTN",
    "форма n 1 т": "TTN",
    "товарно-транспортная накладная": "TTN",
    "товарно транспортная накладная": "TTN",
    "invoice": "INVOICE",
    "инвойс": "INVOICE",
    "счет-фактура": "INVOICE",
    "счёт-фактура": "INVOICE",
    "счет фактура": "INVOICE",
    "счёт фактура": "INVOICE",
    "универсальный передаточный документ": "UPD",
    "receipt": "RECEIPT",
    "retail_receipt": "RECEIPT",
    "чек": "RECEIPT",
    "кассовый чек": "RECEIPT",
    "товарный чек": "RECEIPT",
}
INVOICE_DOC_TYPES = {"UPD", "TORG-12", "TTN", "INVOICE"}


def _normalize_search_text(value: str) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_doc_type(value: str | None) -> str:
    if not value:
        return ""
    lowered = _normalize_search_text(value)
    return DOC_TYPE_ALIASES.get(lowered, lowered)


def _has_invoice_keyword(raw_text: str) -> bool:
    text = _normalize_search_text(raw_text or "")
    return any(token in text for token in KEYWORD_TOKENS)


def _has_receipt_keyword(raw_text: str) -> bool:
    text = _normalize_search_text(raw_text or "")
    return any(token in text for token in RECEIPT_KEYWORD_TOKENS)


def _has_positive_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, ValueError):
        return False


def _has_money_rows(items: list[InvoiceItem]) -> bool:
    for item in items:
        if _has_positive_number(item.unit_price) or _has_positive_number(item.total_cost):
            return True
    return False


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
    has_receipt_keyword = bool(llm_data.get("has_receipt_keyword"))
    if doc_type == "RECEIPT":
        return True
    if doc_type in INVOICE_DOC_TYPES:
        return True

    has_keyword = _has_invoice_keyword(raw_text)
    has_receipt_text_keyword = _has_receipt_keyword(raw_text)
    numeric_rows = 0
    for item in items:
        if item.unit_amount is not None or item.unit_price is not None or item.total_cost is not None:
            numeric_rows += 1

    has_invoice_number = bool(parsed.invoice_number and re.search(r"\d", str(parsed.invoice_number)))
    has_vendor = bool(parsed.vendor_name and str(parsed.vendor_name).strip())
    has_total = _has_positive_number(parsed.total_amount)
    has_core_meta = has_invoice_number or has_total
    has_meta = has_core_meta or (has_vendor and bool(parsed.invoice_date))
    has_money = _has_money_rows(items)

    if has_receipt_keyword and numeric_rows >= 1:
        return True

    if has_llm_keyword is False:
        if source_type == "image":
            if has_receipt_text_keyword and numeric_rows >= 1:
                return True
            return has_core_meta and has_money and numeric_rows >= 1
        return has_core_meta and has_money and numeric_rows >= 1
    if has_llm_keyword is True and numeric_rows >= 1:
        return True

    if has_keyword and numeric_rows >= 1:
        return True
    if has_receipt_text_keyword and numeric_rows >= 1:
        return True
    if has_core_meta and has_money and numeric_rows >= 1:
        return True
    if has_meta and numeric_rows >= 1 and len(items) >= 2:
        return True
    if source_type != "image" and numeric_rows >= 3 and len(items) >= 3:
        return True
    if source_type == "image" and has_money and len(items) >= 2:
        return True
    return False
