"""Standalone modular resolver for nomenclature and quantity units."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from app.config import settings
from app.schemas import InvoiceItem
from app.services.invoice_flow.llm_unit_resolver import LlmUnitDecision, LlmUnitResolver
from app.services.invoice_flow.models import CatalogEntry, FlowSuggestion
from app.services.invoice_flow.owner_rules import OwnerConversionRule, OwnerRuleBook
from app.services.invoice_flow.unit_conversion import (
    ConversionResult,
    infer_pack_size,
    infer_source_unit,
    normalize_unit,
    propose_conversion,
)


def _normalize_name(value: str) -> str:
    lowered = (value or "").strip().lower()
    lowered = re.sub(r"[^\w\s]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _clone_item(item: InvoiceItem) -> InvoiceItem:
    return item.model_copy(deep=True)


def _rulebook_path() -> Path:
    path = Path(settings.invoice_flow_owner_rules_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    return path


def _conversion_from_owner_rule(
    *,
    rule: OwnerConversionRule,
    quantity: Decimal,
    source_unit: str | None,
) -> ConversionResult | None:
    normalized_source = normalize_unit(source_unit) or "pcs"
    if rule.piece_mass_g is not None:
        target_unit = normalize_unit(rule.target_unit) or "g"
        target_quantity = quantity * rule.piece_mass_g
        return ConversionResult(
            source_unit=normalized_source,
            target_unit=target_unit,
            source_quantity=quantity,
            target_quantity=target_quantity,
            factor=rule.piece_mass_g,
            confidence="high",
            reason="piece_to_mass_conversion",
        )
    if rule.piece_volume_ml is not None:
        target_unit = normalize_unit(rule.target_unit) or "ml"
        target_quantity = quantity * rule.piece_volume_ml
        return ConversionResult(
            source_unit=normalized_source,
            target_unit=target_unit,
            source_quantity=quantity,
            target_quantity=target_quantity,
            factor=rule.piece_volume_ml,
            confidence="high",
            reason="piece_to_volume_conversion",
        )
    return None


def _conversion_from_llm(
    *,
    decision: LlmUnitDecision,
    quantity: Decimal,
    source_unit: str | None,
) -> ConversionResult | None:
    normalized_source = normalize_unit(source_unit) or "pcs"
    if decision.decision == "convert_to_mass" and decision.piece_mass_g is not None:
        target_unit = normalize_unit(decision.target_unit) or "g"
        target_quantity = quantity * decision.piece_mass_g
        return ConversionResult(
            source_unit=normalized_source,
            target_unit=target_unit,
            source_quantity=quantity,
            target_quantity=target_quantity,
            factor=decision.piece_mass_g,
            confidence=decision.confidence,
            reason="piece_to_mass_conversion",
        )
    if decision.decision == "convert_to_volume" and decision.piece_volume_ml is not None:
        target_unit = normalize_unit(decision.target_unit) or "ml"
        target_quantity = quantity * decision.piece_volume_ml
        return ConversionResult(
            source_unit=normalized_source,
            target_unit=target_unit,
            source_quantity=quantity,
            target_quantity=target_quantity,
            factor=decision.piece_volume_ml,
            confidence=decision.confidence,
            reason="piece_to_volume_conversion",
        )
    return None


class InvoiceModularResolver:
    """Experimental resolver with deterministic unit conversion logic."""

    def __init__(self) -> None:
        self._rulebook = OwnerRuleBook(_rulebook_path())
        self._llm = LlmUnitResolver()

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

            normalized_name = _normalize_name(item.name)
            match = catalog_index.get(normalized_name) if enable_catalog_match else None
            preferred_unit = match.stock_unit if match else None

            if match and "catalogProductId" not in item.extras:
                item.extras["catalogProductId"] = match.product_id
                if match.category and "catalogCategory" not in item.extras:
                    item.extras["catalogCategory"] = match.category

            owner_rule = self._rulebook.match(item.name) if enable_unit_conversion else None
            inferred_unit = infer_source_unit(item.unit_measure, item.name)
            treat_as_pieces = inferred_unit in {"pcs", "pack"} or (
                not item.unit_measure and bool(owner_rule or infer_pack_size(item.name))
            )
            source_quantity = (
                item.unit_amount
                if treat_as_pieces and item.unit_amount is not None
                else (item.supply_quantity or item.unit_amount)
            )
            source_unit = item.unit_measure or inferred_unit

            conversion: ConversionResult | None = None
            if enable_unit_conversion and source_quantity is not None:
                if owner_rule is not None:
                    conversion = _conversion_from_owner_rule(
                        rule=owner_rule,
                        quantity=source_quantity,
                        source_unit=source_unit,
                    )
                    if conversion is not None:
                        item.extras["flowOwnerRule"] = owner_rule.pattern

                if conversion is None:
                    conversion = propose_conversion(
                        quantity=source_quantity,
                        source_unit=source_unit,
                        item_name=item.name,
                        preferred_stock_unit=preferred_unit,
                        density_g_per_ml=owner_rule.density_g_per_ml if owner_rule else None,
                    )

                if conversion is None and settings.invoice_flow_enable_llm_fallback:
                    llm_decision = self._llm.resolve(
                        item_name=item.name,
                        unit_measure=item.unit_measure,
                        unit_amount=item.unit_amount,
                        supply_quantity=item.supply_quantity,
                        preferred_stock_unit=preferred_unit,
                        piece_mass_g=owner_rule.piece_mass_g if owner_rule else None,
                        piece_volume_ml=owner_rule.piece_volume_ml if owner_rule else None,
                    )
                    if llm_decision is not None:
                        conversion = _conversion_from_llm(
                            decision=llm_decision,
                            quantity=source_quantity,
                            source_unit=source_unit,
                        )
                        if conversion is not None:
                            item.extras["flowLlmDecision"] = llm_decision.decision

            if conversion is not None:
                target_unit = conversion.target_unit
                target_quantity = conversion.target_quantity
                if target_unit and normalize_unit(item.unit_measure) != target_unit:
                    item.unit_measure = target_unit
                    row_changed = True
                if target_quantity is not None and target_quantity != source_quantity:
                    item.supply_quantity = target_quantity
                    item.unit_amount = target_quantity
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
