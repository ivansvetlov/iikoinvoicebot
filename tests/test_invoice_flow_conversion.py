from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.schemas import InvoiceItem
from app.services.invoice_flow import CatalogEntry, InvoiceFlowRunner
from app.services.invoice_flow.llm_unit_resolver import LlmUnitDecision
from app.services.invoice_flow.unit_conversion import infer_source_unit, propose_conversion


class InvoiceFlowConversionTests(unittest.TestCase):
    def test_density_conversion_volume_to_mass(self) -> None:
        conversion = propose_conversion(
            quantity=Decimal("1"),
            source_unit="l",
            item_name="Milk",
            preferred_stock_unit="g",
            density_g_per_ml=Decimal("1.03"),
        )
        self.assertIsNotNone(conversion)
        assert conversion is not None
        self.assertEqual(conversion.target_unit, "g")
        self.assertEqual(conversion.target_quantity, Decimal("1030"))
        self.assertEqual(conversion.reason, "density_unit_conversion")

    def test_modular_mode_converts_pcs_to_mass_for_milk(self) -> None:
        items = [InvoiceItem(name="Молоко 1л (12 шт/кор)", unit_measure="шт", supply_quantity=Decimal("2"))]
        catalog = [CatalogEntry(product_id="P1", name="Молоко 1л (12 шт/кор)", stock_unit="г")]

        with patch("app.services.invoice_flow.resolver.settings.invoice_flow_owner_rules_path", "tmp/missing.json"):
            result = InvoiceFlowRunner(mode="modular").execute(items, catalog=catalog)

        self.assertEqual(result.mode, "modular")
        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "g")
        self.assertEqual(result.output_items[0].unit_amount, Decimal("2060"))
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("2060"))
        self.assertEqual(result.output_items[0].extras.get("flowConversionReason"), "piece_to_mass_conversion")

    def test_owner_rule_overrides_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.json"
            rules_payload = {
                "rules": [
                    {
                        "pattern": "(?i)кофе",
                        "target_unit": "g",
                        "piece_mass_g": 1000,
                    }
                ]
            }
            rules_path.write_text(json.dumps(rules_payload, ensure_ascii=False), encoding="utf-8")

            items = [InvoiceItem(name="Кофе зерно premium", unit_measure="шт", supply_quantity=Decimal("3"))]
            with patch(
                "app.services.invoice_flow.resolver.settings.invoice_flow_owner_rules_path",
                str(rules_path),
            ):
                result = InvoiceFlowRunner(mode="modular").execute(items, catalog=[])

        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "g")
        self.assertEqual(result.output_items[0].unit_amount, Decimal("3000"))
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("3000"))
        self.assertEqual(result.output_items[0].extras.get("flowOwnerRule"), "(?i)кофе")

    def test_infer_source_unit_from_pack_size_when_unit_missing(self) -> None:
        self.assertEqual(infer_source_unit(None, "Вода питьевая 18,9 л"), "pcs")

    def test_modular_mode_converts_missing_unit_line_by_pack_size(self) -> None:
        items = [InvoiceItem(name="Вода питьевая 18,9 л", unit_measure=None, unit_amount=Decimal("4"))]

        with patch("app.services.invoice_flow.resolver.settings.invoice_flow_owner_rules_path", "tmp/missing.json"):
            result = InvoiceFlowRunner(mode="modular").execute(items, catalog=[])

        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "ml")
        self.assertEqual(result.output_items[0].unit_amount, Decimal("75600"))
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("75600"))
        self.assertEqual(result.output_items[0].extras.get("flowConversionReason"), "piece_to_volume_conversion")

    def test_owner_rule_converts_when_unit_missing_and_prefers_unit_amount(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.json"
            rules_payload = {
                "rules": [
                    {
                        "pattern": "(?i)кофе.*зерн",
                        "target_unit": "g",
                        "piece_mass_g": 1000,
                    }
                ]
            }
            rules_path.write_text(json.dumps(rules_payload, ensure_ascii=False), encoding="utf-8")

            items = [
                InvoiceItem(
                    name="Кофе зерно premium",
                    unit_measure=None,
                    unit_amount=Decimal("10"),
                    supply_quantity=Decimal("1"),
                )
            ]
            with patch("app.services.invoice_flow.resolver.settings.invoice_flow_owner_rules_path", str(rules_path)):
                result = InvoiceFlowRunner(mode="modular").execute(items, catalog=[])

        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "g")
        self.assertEqual(result.output_items[0].unit_amount, Decimal("10000"))
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("10000"))

    def test_llm_fallback_converts_ambiguous_item(self) -> None:
        items = [
            InvoiceItem(
                name="Кофе зерно special",
                unit_measure=None,
                unit_amount=Decimal("10"),
                supply_quantity=Decimal("10"),
            )
        ]
        llm_decision = LlmUnitDecision(
            decision="convert_to_mass",
            target_unit="g",
            piece_mass_g=Decimal("1000"),
            piece_volume_ml=None,
            confidence="high",
            reason="default coffee bean bag",
        )
        with patch("app.services.invoice_flow.resolver.settings.invoice_flow_owner_rules_path", "tmp/missing.json"):
            with patch("app.services.invoice_flow.resolver.settings.invoice_flow_enable_llm_fallback", True):
                with patch(
                    "app.services.invoice_flow.resolver.LlmUnitResolver.resolve",
                    return_value=llm_decision,
                ):
                    result = InvoiceFlowRunner(mode="modular").execute(items, catalog=[])

        self.assertEqual(result.changed_rows, 1)
        self.assertEqual(result.output_items[0].unit_measure, "g")
        self.assertEqual(result.output_items[0].unit_amount, Decimal("10000"))
        self.assertEqual(result.output_items[0].supply_quantity, Decimal("10000"))
        self.assertEqual(result.output_items[0].extras.get("flowLlmDecision"), "convert_to_mass")


if __name__ == "__main__":
    unittest.main()
