"""Unit tests for MAX invoice bot (no live MAX API)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.bot.invoice_keyboards import build_invoice_actions
from experiments.max_invoice_bot.config import MaxInvoiceSettings
from experiments.max_invoice_bot.keyboards import dict_to_markup
from experiments.max_invoice_bot.messaging import (
    keyboard_to_edit_attachments,
    prepare_outgoing_text,
    split_text,
)
from experiments.max_invoice_bot.task_watcher import (
    _keyboard_for_result,
    _normalize_status,
    _result_from_task,
)
from experiments.max_invoice_bot.attachments import has_downloadable_attachments
from experiments.max_invoice_bot.bot import _auth_failure_message
from experiments.max_invoice_bot.user_ids import parse_store_user_id, storage_dir_key, store_user_id
from maxapi.enums.attachment import AttachmentType


class MaxInvoiceBotTests(unittest.TestCase):
    def test_store_user_id_namespace(self) -> None:
        self.assertEqual(store_user_id(42), "max:42")
        self.assertEqual(parse_store_user_id("max:42"), 42)
        self.assertIsNone(parse_store_user_id("6106711925"))

    def test_dict_to_max_markup(self) -> None:
        kb = build_invoice_actions("req-abc")
        markup = dict_to_markup(kb)
        self.assertIsNotNone(markup)

    def test_keyboard_to_edit_attachments_clears_when_none(self) -> None:
        self.assertEqual(keyboard_to_edit_attachments(None), [])

    def test_keyboard_to_edit_attachments_replaces_when_set(self) -> None:
        kb = build_invoice_actions("req-abc")
        self.assertIsNotNone(keyboard_to_edit_attachments(kb))

    def test_split_text_chunks(self) -> None:
        chunks = split_text("a\n" + "b" * 5000, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(len(c) for c in chunks), 1000)

    def test_normalize_task_status(self) -> None:
        self.assertEqual(_normalize_status("done"), "done")
        self.assertEqual(_normalize_status("ok"), "done")
        self.assertEqual(_normalize_status("error"), "error")

    def test_result_from_task_maps_ok_status(self) -> None:
        payload = _result_from_task(
            {
                "request_id": "20260630_144016_272_____183900520",
                "status": "ok",
                "message": "Готово.",
                "iiko_uploaded": True,
            }
        )
        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("iiko_uploaded"))

    def test_keyboard_for_ok_result(self) -> None:
        kb = _keyboard_for_result({"status": "ok", "request_id": "r1"})
        self.assertIsNotNone(kb)
        self.assertIn("inline_keyboard", kb or {})

    def test_auth_failure_network(self) -> None:
        msg = _auth_failure_message(OSError("[Errno 11001] getaddrinfo failed"))
        self.assertEqual(
            msg,
            "Сервер интеграции с iiko сейчас недоступен.\n"
            "Проверьте интернет или VPN и повторите позже.\n"
            "Веб-вход в iikoWeb и API — разные контуры.\n\n"
            "Введите логин снова:",
        )

    def test_auth_failure_credentials(self) -> None:
        msg = _auth_failure_message(RuntimeError("IIKO auth failed: status=401"))
        self.assertIn("Не удалось авторизоваться", msg)

    def test_allowed_ids_parsing(self) -> None:
        with patch.dict("os.environ", {"MAX_INVOICE_BOT_ALLOWED_USER_IDS": "1, 2;3"}, clear=False):
            s = MaxInvoiceSettings()
            self.assertEqual(s.allowed_ids(), {1, 2, 3})

    def test_forwarded_image_detected_without_body_attachments(self) -> None:
        image = SimpleNamespace(type=AttachmentType.IMAGE)
        message = SimpleNamespace(
            body=SimpleNamespace(attachments=[], text="пересланный текст"),
            link=SimpleNamespace(message=SimpleNamespace(attachments=[image])),
        )
        self.assertTrue(has_downloadable_attachments(message))


if __name__ == "__main__":
    unittest.main()
