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


if __name__ == "__main__":
    unittest.main()
