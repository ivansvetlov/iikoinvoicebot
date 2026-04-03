from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from app.iiko.idempotency_store import IikoImportIdempotencyStore
from app.iiko.incoming_invoice_mapper import IncomingInvoiceMapper
from app.schemas import InvoiceItem, InvoiceParseResult


class IncomingInvoiceMapperTests(unittest.TestCase):
    def test_map_payload_applies_pack_conversion_and_vat_fields(self) -> None:
        mapper = IncomingInvoiceMapper(
            default_store_id="store-guid",
            default_supplier_id="supplier-guid",
            default_status="NEW",
        )
        parsed = InvoiceParseResult(
            source_type="image",
            raw_text="",
            invoice_number="INV-77",
            invoice_date="12.03.2026",
            vendor_name="Vendor A",
            total_amount=Decimal("240"),
            items=[],
            warnings=[],
        )
        item = InvoiceItem(
            name="Milk 1L",
            unit_measure="pack 10",
            unit_amount=Decimal("2"),
            unit_price=Decimal("120"),
            cost_without_tax=Decimal("200"),
            tax_rate=Decimal("20"),
            tax_amount=Decimal("40"),
            cost_with_tax=Decimal("240"),
        )

        payload = mapper.map_payload(parsed=parsed, items=[item], request_id="req-map-1")
        line = payload["items"]["item"][0]

        self.assertEqual(payload["defaultStore"], "store-guid")
        self.assertEqual(payload["supplier"], "supplier-guid")
        self.assertEqual(payload["status"], "NEW")
        self.assertEqual(payload["documentNumber"], "INV-77")
        self.assertEqual(line["amount"], 20.0)
        self.assertEqual(line["actualAmount"], 20.0)
        self.assertEqual(line["price"], 12.0)
        self.assertEqual(line["priceWithoutVat"], 10.0)
        self.assertEqual(line["vatPercent"], 20.0)
        self.assertEqual(line["vatSum"], 40.0)
        self.assertEqual(line["sum"], 240.0)
        self.assertEqual(line["product"], "Milk 1L")

    def test_external_key_is_deterministic(self) -> None:
        mapper = IncomingInvoiceMapper(default_store_id="s", default_supplier_id="p")
        parsed = InvoiceParseResult(
            source_type="image",
            raw_text="",
            invoice_number="A-1",
            invoice_date="12.03.2026",
            vendor_name="Vendor B",
            total_amount=Decimal("10"),
            items=[],
            warnings=[],
        )
        item = InvoiceItem(name="Item", cost_with_tax=Decimal("10"))

        key1 = mapper.build_external_key(parsed, [item])
        key2 = mapper.build_external_key(parsed, [item])
        self.assertEqual(key1, key2)


class IikoImportIdempotencyStoreTests(unittest.TestCase):
    def test_record_then_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "iiko_registry.jsonl"
            store = IikoImportIdempotencyStore(store_path)

            self.assertFalse(store.exists("ext-1"))
            store.record(external_key="ext-1", request_id="req-1", mode="server", details={"ok": True})
            self.assertTrue(store.exists("ext-1"))
            self.assertFalse(store.exists("ext-2"))


if __name__ == "__main__":
    unittest.main()

