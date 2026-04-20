"""Unit normalization and conversion helpers for modular flow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


_UNIT_ALIASES: dict[str, str] = {
    "pcs": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
    "шт": "pcs",
    "штука": "pcs",
    "штук": "pcs",
    "pack": "pack",
    "pkg": "pack",
    "уп": "pack",
    "упак": "pack",
    "упаковка": "pack",
    "ml": "ml",
    "мл": "ml",
    "l": "l",
    "л": "l",
    "liter": "l",
    "литр": "l",
    "litre": "l",
    "g": "g",
    "гр": "g",
    "г": "g",
    "kg": "kg",
    "кг": "kg",
}

_DIMENSION: dict[str, str] = {
    "ml": "volume",
    "l": "volume",
    "g": "mass",
    "kg": "mass",
}

_BASE_FACTOR: dict[str, Decimal] = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "g": Decimal("1"),
    "kg": Decimal("1000"),
}

_PACK_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|кг|kg|г|гр|g)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ConversionResult:
    source_unit: str
    target_unit: str
    source_quantity: Decimal
    target_quantity: Decimal
    factor: Decimal
    confidence: Literal["low", "medium", "high"]
    reason: str


def normalize_unit(raw_unit: str | None) -> str | None:
    if not raw_unit:
        return None
    key = str(raw_unit).strip().lower()
    key = re.sub(r"[^\w]+", "", key)
    return _UNIT_ALIASES.get(key)


def convert_between_units(quantity: Decimal, source_unit: str, target_unit: str) -> Decimal | None:
    if source_unit == target_unit:
        return quantity
    if source_unit not in _DIMENSION or target_unit not in _DIMENSION:
        return None
    if _DIMENSION[source_unit] != _DIMENSION[target_unit]:
        return None
    base_qty = quantity * _BASE_FACTOR[source_unit]
    return base_qty / _BASE_FACTOR[target_unit]


def infer_pack_size(item_name: str) -> tuple[str, Decimal] | None:
    if not item_name:
        return None
    match = _PACK_SIZE_RE.search(item_name.lower())
    if not match:
        return None
    amount_raw, unit_raw = match.groups()
    normalized = normalize_unit(unit_raw)
    if not normalized:
        return None
    amount = Decimal(amount_raw.replace(",", "."))
    if normalized == "l":
        return ("ml", amount * Decimal("1000"))
    if normalized == "kg":
        return ("g", amount * Decimal("1000"))
    if normalized in {"ml", "g"}:
        return (normalized, amount)
    return None


def propose_conversion(
    *,
    quantity: Decimal | None,
    source_unit: str | None,
    item_name: str,
    preferred_stock_unit: str | None,
) -> ConversionResult | None:
    if quantity is None or quantity <= 0:
        return None

    normalized_source = normalize_unit(source_unit)
    normalized_target = normalize_unit(preferred_stock_unit)
    if normalized_source and normalized_target:
        direct_qty = convert_between_units(quantity, normalized_source, normalized_target)
        if direct_qty is not None:
            return ConversionResult(
                source_unit=normalized_source,
                target_unit=normalized_target,
                source_quantity=quantity,
                target_quantity=direct_qty,
                factor=(direct_qty / quantity) if quantity else Decimal("1"),
                confidence="high",
                reason="direct_unit_conversion",
            )

    if normalized_source in {"pcs", "pack"}:
        pack = infer_pack_size(item_name)
        if pack:
            inferred_unit, inferred_amount = pack
            if normalized_target and normalize_unit(normalized_target) == inferred_unit:
                target_unit = normalized_target
            else:
                target_unit = inferred_unit
            target_qty = quantity * inferred_amount
            return ConversionResult(
                source_unit=normalized_source,
                target_unit=target_unit,
                source_quantity=quantity,
                target_quantity=target_qty,
                factor=inferred_amount,
                confidence="medium",
                reason="inferred_from_item_name",
            )

    if normalized_source and normalized_target and normalized_source == normalized_target:
        return ConversionResult(
            source_unit=normalized_source,
            target_unit=normalized_target,
            source_quantity=quantity,
            target_quantity=quantity,
            factor=Decimal("1"),
            confidence="high",
            reason="same_unit",
        )

    return None
