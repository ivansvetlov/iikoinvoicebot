from __future__ import annotations

from decimal import Decimal
import unittest

from app.schemas import InvoiceItem, InvoiceParseResult
from app.services.invoice_validator import is_likely_invoice
from app.services.pipeline import InvoicePipelineService


def _sample_item(*, amount: str = "10", price: str = "65000", total: str = "780000") -> InvoiceItem:
    return InvoiceItem(
        name="Холодильник LG",
        unit_amount=Decimal(amount),
        unit_price=Decimal(price),
        total_cost=Decimal(total),
    )


def _sample_parse_result(*, total_amount: str | None, source_type: str = "image") -> InvoiceParseResult:
    return InvoiceParseResult(
        source_type=source_type,
        raw_text="",
        invoice_number="5",
        invoice_date="26 ноября 2025 г.",
        vendor_name="ИП Абрамов Г. С.",
        total_amount=Decimal(total_amount) if total_amount is not None else None,
        items=[],
        warnings=[],
    )


class InvoiceValidatorTests(unittest.TestCase):
    def test_accepts_schet_faktura_doc_type_alias(self) -> None:
        parsed = _sample_parse_result(total_amount=None)
        items = [_sample_item()]
        llm_data = {"document_type": "счет-фактура", "has_invoice_keyword": False}

        result = is_likely_invoice(
            items=items,
            raw_text="",
            parsed=parsed,
            source_type="pdf",
            llm_data=llm_data,
        )

        self.assertTrue(result)

    def test_accepts_strong_metadata_even_without_keyword_for_non_image(self) -> None:
        parsed = _sample_parse_result(total_amount="780000", source_type="pdf")
        items = [_sample_item()]
        llm_data = {
            "document_type": "OTHER",
            "has_invoice_keyword": False,
        }

        result = is_likely_invoice(
            items=items,
            raw_text="",
            parsed=parsed,
            source_type="pdf",
            llm_data=llm_data,
        )

        self.assertTrue(result)

    def test_accepts_image_with_strong_metadata_even_without_keyword(self) -> None:
        parsed = _sample_parse_result(total_amount="780000", source_type="image")
        items = [_sample_item()]
        llm_data = {
            "document_type": "OTHER",
            "has_invoice_keyword": False,
        }

        result = is_likely_invoice(
            items=items,
            raw_text="",
            parsed=parsed,
            source_type="image",
            llm_data=llm_data,
        )

        self.assertTrue(result)

    def test_accepts_receipt_doc_type(self) -> None:
        parsed = _sample_parse_result(total_amount="780000", source_type="image")
        items = [_sample_item()]
        llm_data = {"document_type": "кассовый чек", "has_invoice_keyword": False}

        result = is_likely_invoice(
            items=items,
            raw_text="",
            parsed=parsed,
            source_type="image",
            llm_data=llm_data,
        )

        self.assertTrue(result)

    def test_accepts_receipt_keyword_in_raw_text(self) -> None:
        parsed = _sample_parse_result(total_amount=None, source_type="image")
        items = [_sample_item()]
        llm_data = {"document_type": "OTHER", "has_invoice_keyword": False, "has_receipt_keyword": True}

        result = is_likely_invoice(
            items=items,
            raw_text="КАССОВЫЙ ЧЕК. ПРОДАЖА ТОВАРА.",
            parsed=parsed,
            source_type="image",
            llm_data=llm_data,
        )

        self.assertTrue(result)

    def test_accepts_ttn_doc_type_with_spaced_hyphen(self) -> None:
        parsed = _sample_parse_result(total_amount=None, source_type="pdf")
        items = [_sample_item()]
        llm_data = {"document_type": "товарно - транспортная накладная", "has_invoice_keyword": False}

        result = is_likely_invoice(
            items=items,
            raw_text="",
            parsed=parsed,
            source_type="pdf",
            llm_data=llm_data,
        )

        self.assertTrue(result)


class PipelineGarbageGuardTests(unittest.TestCase):
    def test_does_not_reject_strong_invoice_signals(self) -> None:
        service = InvoicePipelineService()
        items = [_sample_item()]
        llm_data = {
            "document_type": "OTHER",
            "has_invoice_keyword": False,
            "invoice_number": "5",
            "invoice_date": "26 ноября 2025 г.",
            "total_amount": 780000,
        }

        reasons = service._detect_garbage_items(items, llm_data)

        self.assertNotIn("has_invoice_keyword=false при наличии позиций", reasons)

    def test_rejects_keyword_mismatch_without_strong_signals(self) -> None:
        service = InvoicePipelineService()
        items = [
            InvoiceItem(
                name="Товар",
                unit_amount=Decimal("0"),
                unit_price=Decimal("0"),
                total_cost=Decimal("0"),
            )
        ]
        llm_data = {"document_type": "OTHER", "has_invoice_keyword": False}

        reasons = service._detect_garbage_items(items, llm_data)

        self.assertIn("has_invoice_keyword=false при наличии позиций", reasons)

    def test_does_not_reject_receipt_signals(self) -> None:
        service = InvoicePipelineService()
        items = [_sample_item()]
        llm_data = {"document_type": "кассовый чек", "has_invoice_keyword": False, "has_receipt_keyword": True}

        reasons = service._detect_garbage_items(items, llm_data)

        self.assertNotIn("has_invoice_keyword=false при наличии позиций", reasons)

    def test_detects_receipt_like_ocr_text(self) -> None:
        service = InvoicePipelineService()
        text = "kaccosbid yek prodaja tobara itogo k oplate smena n:0053"
        self.assertTrue(service._looks_like_receipt_text(text))

    def test_does_not_detect_invoice_text_as_receipt(self) -> None:
        service = InvoicePipelineService()
        text = "ТОВАРНАЯ НАКЛАДНАЯ №3064 от 25.04.2016 Количество Цена Сумма без НДС"
        self.assertFalse(service._looks_like_receipt_text(text))

    def test_detects_excel_reference_template_form_1t(self) -> None:
        service = InvoicePipelineService()
        text = (
            "Типовая межотраслевая форма N 1-Т\n"
            "Форма по ОКУД 0345009\n"
            "ТОВАРНО - ТРАНСПОРТНАЯ НАКЛАДНАЯ N\n"
            "полное наименование организации адрес, номер телефона\n"
            "Приложение ... прописью\n"
        )
        self.assertTrue(service._looks_like_excel_reference_template(text))

    def test_does_not_detect_filled_excel_as_reference_template(self) -> None:
        service = InvoicePipelineService()
        text = (
            "Унифицированная форма № ТОРГ-12\n"
            "Форма по ОКУД 0330212\n"
            "ТОВАРНАЯ НАКЛАДНАЯ\n"
            "Молоко 10 95 950\n"
            "Сыр 5 220 1100\n"
            "Хлеб 8 50 400\n"
        )
        self.assertFalse(service._looks_like_excel_reference_template(text))


if __name__ == "__main__":
    unittest.main()
