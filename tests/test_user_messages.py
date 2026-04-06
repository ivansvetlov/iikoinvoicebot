from __future__ import annotations

import unittest

from app.utils.user_messages import format_invoice_markdown


class UserMessagesTests(unittest.TestCase):
    def test_format_invoice_markdown_appends_short_request_code(self) -> None:
        payload = {
            "request_id": "20260406_211530_123_6106711925",
            "parsed": {
                "vendor_name": "Тест Поставщик",
                "invoice_date": "2026-04-06",
                "invoice_number": "15",
                "items": [],
            },
        }

        text = format_invoice_markdown(payload)

        self.assertIn("Код заявки: 211530_123", text)

    def test_format_invoice_markdown_without_request_id_has_no_code(self) -> None:
        payload = {"parsed": {"items": []}}

        text = format_invoice_markdown(payload)

        self.assertNotIn("Код заявки:", text)


if __name__ == "__main__":
    unittest.main()
