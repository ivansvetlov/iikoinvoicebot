from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from app.schemas import InvoiceItem
from app.services.invoice_flow import CatalogEntry, InvoiceFlowRunner, resolve_flow_mode


class InvoiceFlowModeTests(unittest.TestCase):
    def test_unknown_mode_falls_back_to_legacy(self) -> None:
        self.assertEqual(resolve_flow_mode("unknown"), "legacy")
        self.assertEqual(resolve_flow_mode(""), "legacy")
        self.assertEqual(resolve_flow_mode(None), "legacy")
        self.assertEqual(resolve_flow_mode("shadow"), "shadow")

    def test_legacy_mode_keeps_items_without_suggestions(self) -> None:
        items = [InvoiceItem(name="Milk 1l", unit_measure="шт", supply_quantity=Decimal("2"))]
        result = InvoiceFlowRunner(mode="legacy").execute(items)
        self.assertEqual(result.mode, "legacy")
        self.assertEqual(result.changed_rows, 0)
        self.assertEqual(len(result.suggestions), 0)
        self.assertEqual(result.output_items[0].unit_measure, "шт")
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("2"))

    def test_runner_uses_settings_mode_when_not_passed(self) -> None:
        items = [InvoiceItem(name="Milk 1l", unit_measure="шт", supply_quantity=Decimal("1"))]
        with patch("app.services.invoice_flow.runner.settings.invoice_flow_mode", "shadow"):
            result = InvoiceFlowRunner(mode=None).execute(items)
        self.assertEqual(result.mode, "shadow")

    def test_shadow_mode_produces_suggestions_but_keeps_legacy_output(self) -> None:
        items = [InvoiceItem(name="Syrup Vanilla 1l", unit_measure="шт", supply_quantity=Decimal("2"))]
        result = InvoiceFlowRunner(mode="shadow").execute(items)
        self.assertEqual(result.mode, "shadow")
        self.assertGreaterEqual(len(result.suggestions), 1)
        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "шт")
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("2"))
        self.assertEqual(result.modular_items[0].unit_measure, "ml")
        self.assertEqual(result.modular_items[0].supply_quantity, Decimal("2000"))

    def test_modular_mode_applies_direct_catalog_conversion(self) -> None:
        items = [InvoiceItem(name="Milk 1l", unit_measure="л", supply_quantity=Decimal("2"))]
        catalog = [CatalogEntry(product_id="P1", name="Milk 1l", stock_unit="мл", category="Dairy")]
        result = InvoiceFlowRunner(mode="modular").execute(items, catalog=catalog)
        self.assertEqual(result.mode, "modular")
        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "ml")
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("2000"))
        self.assertEqual(result.output_items[0].extras.get("catalogProductId"), "P1")

    def test_modular_mode_can_disable_unit_conversion_by_flag(self) -> None:
        items = [InvoiceItem(name="Milk 1l", unit_measure="л", supply_quantity=Decimal("2"))]
        catalog = [CatalogEntry(product_id="P1", name="Milk 1l", stock_unit="мл", category="Dairy")]
        result = InvoiceFlowRunner(
            mode="modular",
            enable_unit_conversion=False,
            enable_catalog_match=True,
        ).execute(items, catalog=catalog)
        self.assertEqual(result.output_items[0].unit_measure, "л")
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("2"))
        self.assertEqual(result.output_items[0].extras.get("catalogProductId"), "P1")


if __name__ == "__main__":
    unittest.main()
