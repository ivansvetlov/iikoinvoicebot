"""Standalone modular resolver for nomenclature and quantity units."""

from __future__ import annotations

import re
from decimal import Decimal

from app.schemas import InvoiceItem
from app.services.invoice_flow.models import CatalogEntry, FlowSuggestion
from app.services.invoice_flow.unit_conversion import normalize_unit, propose_conversion


def _normalize_name(value: str) -> str:
    lowered = (value or "").strip().lower()
    lowered = re.sub(r"[^\w\s]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _clone_item(item: InvoiceItem) -> InvoiceItem:
    return item.model_copy(deep=True)


class InvoiceModularResolver:
    """Experimental resolver with deterministic unit conversion logic."""

    def resolve(
        self,
        items: list[InvoiceItem],
        catalog: list[CatalogEntry] | None = None,
        *,
        enable_unit_conversion: bool = True,
        enable_catalog_match: bool = True,
    ) -> tuple[list[InvoiceItem], list[FlowSuggestion], int, list[str]]:
        catalog = catalog or []
        catalog_index = self._build_catalog_index(catalog)

        resolved_items: list[InvoiceItem] = []
        suggestions: list[FlowSuggestion] = []
        warnings: list[str] = []
        changed_rows = 0

        for idx, source_item in enumerate(items):
            item = _clone_item(source_item)
            notes: list[str] = []
            row_changed = False

            source_quantity = item.supply_quantity or item.unit_amount
            source_unit = item.unit_measure
            normalized_name = _normalize_name(item.name)
            match = catalog_index.get(normalized_name) if enable_catalog_match else None
            preferred_unit = match.stock_unit if match else None

            if match and "catalogProductId" not in item.extras:
                item.extras["catalogProductId"] = match.product_id
                if match.category and "catalogCategory" not in item.extras:
                    item.extras["catalogCategory"] = match.category

            conversion = None
            if enable_unit_conversion:
                conversion = propose_conversion(
                    quantity=source_quantity,
                    source_unit=source_unit,
                    item_name=item.name,
                    preferred_stock_unit=preferred_unit,
                )

            if conversion is not None:
                target_unit = conversion.target_unit
                target_quantity = conversion.target_quantity
                if target_unit and normalize_unit(item.unit_measure) != target_unit:
                    item.unit_measure = target_unit
                    row_changed = True
                if target_quantity is not None and target_quantity != source_quantity:
                    item.supply_quantity = target_quantity
                    row_changed = True
                item.extras["flowConversionReason"] = conversion.reason
                item.extras["flowConversionConfidence"] = conversion.confidence
                item.extras["flowConversionFactor"] = str(conversion.factor)
            else:
                if source_quantity is None:
                    notes.append("missing_quantity")
                if not source_unit:
                    notes.append("missing_unit")
                if source_unit and not normalize_unit(source_unit):
                    notes.append("unknown_unit")
                if notes:
                    warnings.append(f"row={idx + 1}:{','.join(notes)}")

            suggestions.append(
                FlowSuggestion(
                    row_index=idx,
                    source_unit=normalize_unit(source_unit),
                    target_unit=conversion.target_unit if conversion else normalize_unit(source_unit),
                    source_quantity=source_quantity,
                    target_quantity=conversion.target_quantity if conversion else source_quantity,
                    factor=conversion.factor if conversion else None,
                    confidence=conversion.confidence if conversion else "none",
                    reason=conversion.reason if conversion else "",
                    notes=tuple(notes),
                )
            )
            resolved_items.append(item)
            if row_changed:
                changed_rows += 1

        return resolved_items, suggestions, changed_rows, warnings

    def _build_catalog_index(self, catalog: list[CatalogEntry]) -> dict[str, CatalogEntry]:
        index: dict[str, CatalogEntry] = {}
        for item in catalog:
            key = _normalize_name(item.name)
            if key and key not in index:
                index[key] = item
        return index
