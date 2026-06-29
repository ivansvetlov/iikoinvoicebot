"""Unit tests for MAX invoice bot (no live MAX API)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.bot.invoice_keyboards import build_invoice_actions
from experiments.max_invoice_bot.config import MaxInvoiceSettings
from experiments.max_invoice_bot.keyboards import dict_to_markup
from experiments.max_invoice_bot.messaging import split_text
from experiments.max_invoice_bot.task_watcher import _keyboard_for_result, _normalize_status
from experiments.max_invoice_bot.user_ids import store_user_id, parse_store_user_id


class MaxInvoiceBotTests(unittest.TestCase):
    def test_store_user_id_namespace(self) -> None:
        self.assertEqual(store_user_id(42), "max:42")
        self.assertEqual(parse_store_user_id("max:42"), 42)
        self.assertIsNone(parse_store_user_id("6106711925"))

    def test_dict_to_max_markup(self) -> None:
        kb = build_invoice_actions("req-abc")
        markup = dict_to_markup(kb)
        self.assertIsNotNone(markup)

    def test_split_text_chunks(self) -> None:
        chunks = split_text("a\n" + "b" * 5000, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(len(c) for c in chunks), 1000)

    def test_normalize_task_status(self) -> None:
        self.assertEqual(_normalize_status("done"), "done")
        self.assertEqual(_normalize_status("error"), "error")

    def test_keyboard_for_ok_result(self) -> None:
        kb = _keyboard_for_result({"status": "ok", "request_id": "r1"})
        self.assertIsNotNone(kb)
        self.assertIn("inline_keyboard", kb or {})

    def test_allowed_ids_parsing(self) -> None:
        with patch.dict("os.environ", {"MAX_INVOICE_BOT_ALLOWED_USER_IDS": "1, 2;3"}, clear=False):
            s = MaxInvoiceSettings()
            self.assertEqual(s.allowed_ids(), {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
