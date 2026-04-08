"""Экспорт распознанных позиций в файл для ручного импорта в iiko."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas import InvoiceItem


EXPORT_HEADER = [
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "line_no",
    "name",
    "unit_measure",
    "quantity",
    "mass",
    "unit_price",
    "amount_without_tax",
    "tax_rate",
    "tax_amount",
    "amount_with_tax",
    "total_cost",
    "currency",
]


class IikoImportExporter:
    """Генерирует CSV/XLSX с позициями для ручной загрузки в iiko."""

    def __init__(self, export_root: str | Path) -> None:
        self._export_root = Path(export_root)

    def export_items(
        self,
        *,
        request_id: str,
        items: list[InvoiceItem],
        invoice_number: str | None,
        invoice_date: str | None,
        vendor_name: str | None,
        export_format: str,
    ) -> Path:
        normalized_format = (export_format or "csv").strip().lower()
        if normalized_format not in {"csv", "xlsx"}:
            raise ValueError(f"Unsupported iiko import format: {export_format}")

        target_dir = self._export_root / datetime.now().strftime("%Y%m%d") / request_id
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"iiko_import_{request_id}.{normalized_format}"

        rows = self._build_rows(
            items=items,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            vendor_name=vendor_name,
        )
        if normalized_format == "csv":
            self._write_csv(output_path, rows)
        else:
            self._write_xlsx(output_path, rows)
        return output_path

    def _build_rows(
        self,
        *,
        items: list[InvoiceItem],
        invoice_number: str | None,
        invoice_date: str | None,
        vendor_name: str | None,
    ) -> list[list[str]]:
        rows: list[list[str]] = [EXPORT_HEADER]
        for index, item in enumerate(items, start=1):
            rows.append(
                [
                    str(invoice_number or ""),
                    str(invoice_date or ""),
                    str(vendor_name or ""),
                    str(index),
                    str(item.name or ""),
                    str(item.unit_measure or ""),
                    self._to_string(item.unit_amount),
                    self._to_string(item.supply_quantity),
                    self._to_string(item.unit_price),
                    self._to_string(item.cost_without_tax),
                    self._to_string(item.tax_rate),
                    self._to_string(item.tax_amount),
                    self._to_string(item.cost_with_tax),
                    self._to_string(item.total_cost),
                    str(item.currency or "RUB"),
                ]
            )
        return rows

    def _to_string(self, value: object) -> str:
        if value is None:
            return ""
        return str(value)

    def _write_csv(self, path: Path, rows: list[list[str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)

    def _write_xlsx(self, path: Path, rows: list[list[str]]) -> None:
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                if not value:
                    continue
                cell_ref = f"{self._xlsx_col_name(col_index)}{row_index}"
                escaped = escape(str(value))
                cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
            sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        worksheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            + "".join(sheet_rows)
            + "</sheetData></worksheet>"
        )
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Import" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        )

        with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", rels_xml)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    def _xlsx_col_name(self, index: int) -> str:
        result = []
        current = index
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            result.append(chr(ord("A") + remainder))
        return "".join(reversed(result))
