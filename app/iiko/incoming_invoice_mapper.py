"""Mapping from internal invoice models to iikoServer incoming invoice DTO."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.schemas import InvoiceItem, InvoiceParseResult


def _d(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _q(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.0001")))


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return None


class IncomingInvoiceMapper:
    """Builds iikoServer payload for incoming invoice import."""

    def __init__(
        self,
        *,
        default_store_id: str = "",
        default_supplier_id: str = "",
        default_status: str = "NEW",
        default_conception: str = "",
    ) -> None:
        self._default_store_id = default_store_id.strip()
        self._default_supplier_id = default_supplier_id.strip()
        self._default_status = (default_status or "NEW").strip().upper()
        self._default_conception = default_conception.strip()

    def build_external_key(self, parsed: InvoiceParseResult, items: list[InvoiceItem]) -> str:
        supplier = parsed.vendor_name or self._default_supplier_id or "unknown_supplier"
        number = parsed.invoice_number or "unknown_number"
        date = _normalize_date(parsed.invoice_date) or "unknown_date"
        total = parsed.total_amount or sum((_d(i.cost_with_tax) or Decimal("0")) for i in items)
        line_count = len(items)
        fingerprint = f"{supplier}|{number}|{date}|{total}|{line_count}"
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def map_payload(
        self,
        *,
        parsed: InvoiceParseResult,
        items: list[InvoiceItem],
        request_id: str,
    ) -> dict[str, Any]:
        if not items:
            raise ValueError("Cannot build iikoServer payload for empty invoice items")
        if not self._default_store_id:
            raise ValueError("IIKO_SERVER_DEFAULT_STORE_ID is required for iikoServer import")
        if not self._default_supplier_id:
            raise ValueError("IIKO_SERVER_DEFAULT_SUPPLIER_ID is required for iikoServer import")

        mapped_items = [self._map_item(idx + 1, item) for idx, item in enumerate(items)]
        document_number = (parsed.invoice_number or f"AUTO-{request_id[-8:]}").strip()
        total = parsed.total_amount
        if total is None:
            total = sum((_d(item.get("sum")) or Decimal("0")) for item in mapped_items)
        payload: dict[str, Any] = {
            "documentNumber": document_number,
            "dateIncoming": _normalize_date(parsed.invoice_date) or datetime.now().strftime("%d.%m.%Y"),
            "defaultStore": self._default_store_id,
            "supplier": self._default_supplier_id,
            "status": self._default_status,
            "comment": f"request_id={request_id}",
            "incomingDocumentNumber": document_number,
            "items": {"item": mapped_items},
        }
        if self._default_conception:
            payload["conception"] = self._default_conception
        if parsed.vendor_name:
            payload["comment"] += f"; vendor={parsed.vendor_name}"
        if total is not None:
            payload["sum"] = _q(total)
        return payload

    def _map_item(self, index: int, item: InvoiceItem) -> dict[str, Any]:
        extras = item.extras or {}
        coefficient = self._detect_pack_coefficient(item)

        qty = _d(item.unit_amount) or _d(item.supply_quantity) or Decimal("1")
        amount = qty * coefficient
        unit_price = _d(item.unit_price)
        price = (unit_price / coefficient) if (unit_price is not None and coefficient != 0) else unit_price

        amount_with_tax = _d(item.cost_with_tax) or _d(item.total_cost)
        amount_without_tax = _d(item.cost_without_tax)
        tax_sum = _d(item.tax_amount)
        tax_rate = _d(item.tax_rate)

        if amount_with_tax is None and amount_without_tax is not None and tax_sum is not None:
            amount_with_tax = amount_without_tax + tax_sum
        if amount_without_tax is None and amount_with_tax is not None and tax_sum is not None:
            amount_without_tax = amount_with_tax - tax_sum
        if tax_sum is None and amount_with_tax is not None and amount_without_tax is not None:
            tax_sum = amount_with_tax - amount_without_tax
        if tax_rate is None and tax_sum is not None and amount_without_tax and amount_without_tax != 0:
            tax_rate = (tax_sum / amount_without_tax) * Decimal("100")
        if amount_with_tax is None and price is not None:
            amount_with_tax = price * amount
        if amount_without_tax is None:
            amount_without_tax = amount_with_tax

        line: dict[str, Any] = {
            "num": index,
            "sum": _q(amount_with_tax),
            "amount": _q(amount),
            "actualAmount": _q(amount),
            "price": _q(price),
            "priceWithoutVat": _q((amount_without_tax / amount) if (amount_without_tax and amount) else None),
            "vatPercent": _q(tax_rate),
            "vatSum": _q(tax_sum),
        }

        article = extras.get("article") or extras.get("supplier_article")
        product_name = item.name.strip()
        if article:
            line["productArticle"] = article
        else:
            line["product"] = product_name

        container_id = extras.get("container_id")
        if container_id:
            line["containerId"] = container_id
        amount_unit = extras.get("amount_unit_id")
        if amount_unit:
            line["amountUnit"] = amount_unit

        return {k: v for k, v in line.items() if v is not None and v != ""}

    def _detect_pack_coefficient(self, item: InvoiceItem) -> Decimal:
        extras = item.extras or {}
        for key in ("pack_to_base", "pack_coefficient", "uom_factor"):
            value = _d(extras.get(key))
            if value and value > 0:
                return value
        unit = (item.unit_measure or "").strip().lower()
        match = re.search(r"(\d+(?:[.,]\d+)?)", unit.replace(",", "."))
        if match and any(token in unit for token in ("уп", "кор", "box", "pack")):
            parsed = _d(match.group(1))
            if parsed and parsed > 0:
                return parsed
        return Decimal("1")
