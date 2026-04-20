"""Mode switch for legacy/modular/shadow invoice flow experiments."""

from __future__ import annotations

from typing import cast

from app.config import settings
from app.schemas import InvoiceItem
from app.services.invoice_flow.models import CatalogEntry, FlowExecution, FlowMode
from app.services.invoice_flow.resolver import InvoiceModularResolver

_ALLOWED_MODES: tuple[FlowMode, ...] = ("legacy", "shadow", "modular")


def resolve_flow_mode(raw_mode: str | None) -> FlowMode:
    mode = (raw_mode or "").strip().lower()
    if mode in _ALLOWED_MODES:
        return cast(FlowMode, mode)
    return "legacy"


class InvoiceFlowRunner:
    """Standalone flow switcher.

    This runner is intentionally not wired into current production pipeline yet.
    """

    def __init__(
        self,
        mode: str | None = None,
        *,
        enable_unit_conversion: bool | None = None,
        enable_catalog_match: bool | None = None,
    ) -> None:
        self.mode = resolve_flow_mode(mode or settings.invoice_flow_mode)
        self.enable_unit_conversion = (
            settings.invoice_flow_enable_unit_conversion
            if enable_unit_conversion is None
            else bool(enable_unit_conversion)
        )
        self.enable_catalog_match = (
            settings.invoice_flow_enable_catalog_match
            if enable_catalog_match is None
            else bool(enable_catalog_match)
        )
        self._resolver = InvoiceModularResolver()

    def execute(
        self,
        items: list[InvoiceItem],
        catalog: list[CatalogEntry] | None = None,
    ) -> FlowExecution:
        legacy_items = [item.model_copy(deep=True) for item in items]
        modular_items, suggestions, changed_rows, warnings = self._resolver.resolve(
            legacy_items,
            catalog=catalog,
            enable_unit_conversion=self.enable_unit_conversion,
            enable_catalog_match=self.enable_catalog_match,
        )

        if self.mode == "modular":
            output_items = [item.model_copy(deep=True) for item in modular_items]
        else:
            output_items = [item.model_copy(deep=True) for item in legacy_items]

        if self.mode == "legacy":
            suggestions = []
            changed_rows = 0
            warnings = []
            modular_items = [item.model_copy(deep=True) for item in legacy_items]

        return FlowExecution(
            mode=self.mode,
            output_items=output_items,
            legacy_items=legacy_items,
            modular_items=modular_items,
            suggestions=suggestions,
            changed_rows=changed_rows if self.mode != "legacy" else 0,
            warnings=warnings,
        )
