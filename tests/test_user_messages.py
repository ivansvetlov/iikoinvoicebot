from __future__ import annotations

import unittest

from app.bot.messages import Msg
from app.utils.user_messages import format_invoice_markdown, format_user_response, short_request_code


class UserMessagesTests(unittest.TestCase):
    def test_short_request_code_is_five_digits(self) -> None:
        code = short_request_code("20260406_211530_123_6106711925")
        self.assertIsNotNone(code)
        self.assertRegex(code, r"^\d{5}$")

    def test_format_invoice_markdown_appends_short_request_code(self) -> None:
        payload = {
            "request_id": "20260406_211530_123_6106711925",
            "parsed": {
                "vendor_name": "Test Supplier",
                "invoice_date": "2026-04-06",
                "invoice_number": "15",
                "items": [],
            },
        }
        text = format_invoice_markdown(payload)
        code = short_request_code(payload["request_id"])
        self.assertIn(Msg.RESP_CODE.format(code=code), text)

    def test_format_invoice_markdown_without_request_id_has_no_code(self) -> None:
        payload = {"parsed": {"items": []}}
        text = format_invoice_markdown(payload)
        self.assertNotIn("Код заявки:", text)

    def test_format_user_response_uses_plural_error_for_batch(self) -> None:
        payload = {
            "status": "error",
            "batch": True,
            "message": "",
            "error_code": "not_invoice",
            "parsed": {"items": []},
        }
        text = format_user_response(payload)
        self.assertIn(Msg.RESP_ERROR_BATCH, text)
        self.assertNotIn(Msg.RESP_ERROR, text)

    def test_format_user_response_rewrites_not_invoice_message_to_plural_for_batch(self) -> None:
        payload = {
            "status": "error",
            "batch": True,
            "message": Msg.NOT_INVOICE_MESSAGE,
            "error_code": "not_invoice",
            "parsed": {"items": []},
        }
        text = format_user_response(payload)
        self.assertIn(Msg.BATCH_NOT_INVOICE_MESSAGE.strip(), text)
        self.assertNotIn(Msg.NOT_INVOICE_MESSAGE.strip(), text)

    def test_format_user_response_includes_iiko_import_ready_line(self) -> None:
        payload = {
            "status": "ok",
            "parsed": {"items": [{"name": "Item"}], "warnings": []},
            "iiko_uploaded": False,
            "iiko_import_ready": True,
            "iiko_import_format": "csv",
        }
        text = format_user_response(payload)
        self.assertIn(Msg.RESP_IIKO_IMPORT_READY.format(fmt="CSV"), text)

    def test_format_invoice_markdown_includes_iiko_import_ready_notice(self) -> None:
        payload = {
            "parsed": {
                "vendor_name": "Test Supplier",
                "invoice_date": "2026-04-06",
                "invoice_number": "15",
                "items": [],
            },
            "iiko_import_ready": True,
            "iiko_import_format": "xlsx",
        }
        text = format_invoice_markdown(payload)
        self.assertIn(Msg.INVOICE_IMPORT_READY.format(fmt="XLSX"), text)

    def test_format_invoice_markdown_uses_document_level_vat_when_item_vat_missing(self) -> None:
        payload = {
            "parsed": {
                "vendor_name": "Test Supplier",
                "invoice_date": "2026-04-20",
                "invoice_number": "VAT-1",
                "raw_text": "ИТОГО 100,00\nв том числе НДС 20% 16,67",
                "items": [
                    {
                        "name": "Milk",
                        "unit_amount": "1",
                        "unit_price": "100",
                        "cost_with_tax": "100",
                        "tax_amount": None,
                    }
                ],
            },
        }
        text = format_invoice_markdown(payload)
        self.assertIn(Msg.INVOICE_VAT_SUM.format(vat=16.67), text)


if __name__ == "__main__":
    unittest.main()
