from __future__ import annotations

import asyncio
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

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


class PipelineFastParserTests(unittest.TestCase):
    def test_process_uses_fast_parser_before_llm_for_text_source(self) -> None:
        service = InvoicePipelineService()
        raw_text = (
            "INVOICE #12\n"
            "1 Item A 120 3 pcs 360\n"
            "2 Item B 50 4 pcs 200\n"
            "3 Item C 10 2 pcs 20\n"
        )

        async def run_case():
            with patch("app.services.pipeline.FileTextExtractor.extract", return_value=("text", raw_text)):
                with patch("app.services.pipeline.settings.fast_parser_min_chars", 10):
                    with patch.object(
                        service,
                        "_run_llm_pass",
                        new=AsyncMock(side_effect=AssertionError("LLM should not be called for fast-parser success")),
                    ):
                        return await service.process(
                            "invoice.txt",
                            b"stub",
                            push_to_iiko=False,
                            user_id="42",
                            request_id="20260406_120000_000_42",
                        )

        response = asyncio.run(run_case())
        self.assertEqual(response.status, "ok")
        self.assertGreaterEqual(len(response.parsed.items), 2)
        self.assertIn("fast_parser_used", response.parsed.warnings)


class PipelineIikoFallbackTests(unittest.TestCase):
    def test_process_returns_import_ready_when_iiko_upload_fails(self) -> None:
        service = InvoicePipelineService()
        items = [
            InvoiceItem(
                name="Молоко",
                unit_amount=Decimal("2"),
                unit_price=Decimal("100"),
                total_cost=Decimal("200"),
                cost_with_tax=Decimal("200"),
            )
        ]
        fast_result = (
            {
                "document_type": "TORG-12",
                "has_invoice_keyword": True,
                "has_receipt_keyword": False,
                "invoice_number": "15",
                "invoice_date": "2026-04-08",
                "vendor_name": "ООО Тест",
                "total_amount": 200,
            },
            items,
            [],
        )

        async def run_case(tmp_dir: str):
            with patch("app.services.pipeline.FileTextExtractor.extract", return_value=("text", "invoice data")):
                with patch.object(service, "_try_fast_parse", return_value=fast_result):
                    with patch("app.services.pipeline.get_iiko_credentials", return_value=("user", "pass")):
                        with patch.object(
                            service._iiko_client,
                            "upload_invoice_items",
                            new=AsyncMock(side_effect=RuntimeError("iiko api failed")),
                        ):
                            with patch("app.services.pipeline.settings.iiko_transport", "api"):
                                with patch("app.services.pipeline.settings.iiko_import_fallback_enabled", True):
                                    with patch("app.services.pipeline.settings.iiko_import_format", "csv"):
                                        with patch("app.services.pipeline.settings.iiko_import_export_dir", tmp_dir):
                                            service._iiko_import_exporter = service._iiko_import_exporter.__class__(
                                                tmp_dir
                                            )
                                            return await service.process(
                                                "invoice.txt",
                                                b"stub",
                                                push_to_iiko=True,
                                                user_id="42",
                                                request_id="20260408_120000_000_42",
                                            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            response = asyncio.run(run_case(tmp_dir))
            export_exists = bool(response.iiko_import_path) and Path(response.iiko_import_path).exists()

        self.assertEqual(response.status, "ok")
        self.assertFalse(response.iiko_uploaded)
        self.assertTrue(response.iiko_import_ready)
        self.assertEqual(response.iiko_import_format, "csv")
        self.assertTrue(response.iiko_import_path)
        self.assertTrue(export_exists)
        self.assertIn("iiko_import_fallback_csv", response.parsed.warnings)

    def test_process_keeps_error_when_import_fallback_disabled(self) -> None:
        service = InvoicePipelineService()
        items = [
            InvoiceItem(
                name="Молоко",
                unit_amount=Decimal("2"),
                unit_price=Decimal("100"),
                total_cost=Decimal("200"),
                cost_with_tax=Decimal("200"),
            )
        ]
        fast_result = (
            {
                "document_type": "TORG-12",
                "has_invoice_keyword": True,
                "has_receipt_keyword": False,
                "invoice_number": "15",
                "invoice_date": "2026-04-08",
                "vendor_name": "ООО Тест",
                "total_amount": 200,
            },
            items,
            [],
        )

        async def run_case():
            with patch("app.services.pipeline.FileTextExtractor.extract", return_value=("text", "invoice data")):
                with patch.object(service, "_try_fast_parse", return_value=fast_result):
                    with patch("app.services.pipeline.get_iiko_credentials", return_value=("user", "pass")):
                        with patch.object(
                            service._iiko_client,
                            "upload_invoice_items",
                            new=AsyncMock(side_effect=RuntimeError("iiko api failed")),
                        ):
                            with patch("app.services.pipeline.settings.iiko_transport", "api"):
                                with patch("app.services.pipeline.settings.iiko_import_fallback_enabled", False):
                                    return await service.process(
                                        "invoice.txt",
                                        b"stub",
                                        push_to_iiko=True,
                                        user_id="42",
                                        request_id="20260408_121000_000_42",
                                    )

        response = asyncio.run(run_case())
        self.assertEqual(response.status, "error")
        self.assertEqual(response.error_code, "iiko_upload_failed")
        self.assertFalse(response.iiko_import_ready)


class PipelineIikoUploadByRequestTests(unittest.TestCase):
    def test_upload_existing_request_returns_not_found(self) -> None:
        service = InvoicePipelineService()

        with patch.object(service, "_load_saved_request_payload", return_value=None):
            response = asyncio.run(service.upload_existing_request_to_iiko(request_id="missing-42", user_id="42"))

        self.assertEqual(response.status, "error")
        self.assertEqual(response.error_code, "request_not_found")

    def test_upload_existing_request_returns_import_ready_on_api_failure(self) -> None:
        service = InvoicePipelineService()
        payload = {
            "request_id": "req-42",
            "source_type": "pdf",
            "raw_text": "invoice",
            "invoice_number": "15",
            "invoice_date": "2026-04-08",
            "vendor_name": "ООО Тест",
            "total_amount": "200",
            "warnings": [],
            "items": [
                {
                    "name": "Молоко",
                    "unit_amount": "2",
                    "unit_price": "100",
                    "total_cost": "200",
                    "cost_with_tax": "200",
                    "currency": "RUB",
                    "extras": {},
                }
            ],
        }

        async def run_case(tmp_dir: str):
            with patch.object(service, "_load_saved_request_payload", return_value=payload):
                with patch("app.services.pipeline.get_iiko_credentials", return_value=("user", "pass")):
                    with patch.object(
                        service._iiko_client,
                        "upload_invoice_items",
                        new=AsyncMock(side_effect=RuntimeError("iiko api failed")),
                    ):
                        with patch("app.services.pipeline.settings.iiko_transport", "api"):
                            with patch("app.services.pipeline.settings.iiko_import_fallback_enabled", True):
                                with patch("app.services.pipeline.settings.iiko_import_format", "csv"):
                                    with patch("app.services.pipeline.settings.iiko_import_export_dir", tmp_dir):
                                        service._iiko_import_exporter = service._iiko_import_exporter.__class__(tmp_dir)
                                        return await service.upload_existing_request_to_iiko(
                                            request_id="req-42",
                                            user_id="42",
                                        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            response = asyncio.run(run_case(tmp_dir))
            export_exists = bool(response.iiko_import_path) and Path(response.iiko_import_path).exists()

        self.assertEqual(response.status, "ok")
        self.assertFalse(response.iiko_uploaded)
        self.assertTrue(response.iiko_import_ready)
        self.assertEqual(response.iiko_import_format, "csv")
        self.assertTrue(export_exists)


class PipelineCostSummaryTests(unittest.TestCase):
    def test_update_cost_summary_adds_day_and_user_aggregates(self) -> None:
        service = InvoicePipelineService()
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "llm_costs_summary.json"
            with patch("app.services.pipeline.LLM_COSTS_SUMMARY", summary_path):
                with patch.object(service, "_get_usd_rub_rate", return_value=100.0):
                    service._update_cost_summary(
                        user_id="42",
                        request_id="20260406_100000_000_42",
                        cost={"total_cost_usd": 1.25},
                    )
                    service._update_cost_summary(
                        user_id="42",
                        request_id="20260406_120000_000_42",
                        cost={"total_cost_usd": 0.75},
                    )
                    service._update_cost_summary(
                        user_id="99",
                        request_id="20260407_090000_000_99",
                        cost={"total_cost_usd": 2.0},
                    )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["rows"], 3)
        self.assertAlmostEqual(payload["total_usd"], 4.0, places=6)
        self.assertEqual(payload["by_day"]["2026-04-06"]["rows"], 2)
        self.assertEqual(payload["by_day"]["2026-04-07"]["rows"], 1)
        self.assertEqual(payload["by_user"]["42"]["rows"], 2)
        self.assertEqual(payload["by_user"]["99"]["rows"], 1)


if __name__ == "__main__":
    unittest.main()
