from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from app.iiko.import_export import IikoImportExporter
from app.schemas import InvoiceItem


class IikoImportExporterTests(unittest.TestCase):
    def _sample_items(self) -> list[InvoiceItem]:
        return [
            InvoiceItem(
                name="Молоко 1л",
                unit_measure="шт",
                unit_amount=Decimal("10"),
                unit_price=Decimal("89.50"),
                cost_without_tax=Decimal("745.83"),
                tax_rate=Decimal("20"),
                tax_amount=Decimal("149.17"),
                cost_with_tax=Decimal("895.00"),
                total_cost=Decimal("895.00"),
                currency="RUB",
            )
        ]

    def test_export_csv_creates_file_with_header_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = IikoImportExporter(temp_dir)
            path = exporter.export_items(
                request_id="20260408_101010_123_42",
                items=self._sample_items(),
                invoice_number="123",
                invoice_date="2026-04-08",
                vendor_name="ООО Тест",
                export_format="csv",
            )
            content = path.read_text(encoding="utf-8")

        self.assertTrue(path.name.endswith(".csv"))
        self.assertIn("invoice_number,invoice_date,vendor_name,line_no,name", content)
        self.assertIn("Молоко 1л", content)

    def test_export_xlsx_creates_openxml_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = IikoImportExporter(temp_dir)
            path = exporter.export_items(
                request_id="20260408_111111_123_42",
                items=self._sample_items(),
                invoice_number="124",
                invoice_date="2026-04-08",
                vendor_name="ООО Тест",
                export_format="xlsx",
            )
            with ZipFile(path, "r") as archive:
                names = set(archive.namelist())
                sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertTrue(path.name.endswith(".xlsx"))
        self.assertIn("[Content_Types].xml", names)
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("xl/worksheets/sheet1.xml", names)
        self.assertIn("Молоко 1л", sheet_xml)


if __name__ == "__main__":
    unittest.main()
