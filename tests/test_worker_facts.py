import unittest

from app.bot.invoice_keyboards import build_invoice_actions, build_retry_actions


class WorkerActionsTests(unittest.TestCase):
    def test_build_retry_actions_for_transient_error(self) -> None:
        keyboard = build_retry_actions("req-1", "llm_unavailable")
        self.assertIsNotNone(keyboard)
        self.assertEqual(keyboard["inline_keyboard"][0][0]["callback_data"], "inv:retry:req-1")

    def test_build_retry_actions_skips_non_transient_error(self) -> None:
        keyboard = build_retry_actions("req-1", "not_invoice")
        self.assertIsNone(keyboard)

    def test_build_invoice_actions_has_colored_buttons(self) -> None:
        keyboard = build_invoice_actions("req-42", allow_send=True)
        self.assertIsNotNone(keyboard)
        style_by_callback = {
            button["callback_data"]: button.get("style")
            for row in keyboard["inline_keyboard"]
            for button in row
        }
        self.assertEqual(style_by_callback.get("inv:edit:req-42"), "primary")
        self.assertEqual(style_by_callback.get("inv:send:req-42"), "success")
        self.assertEqual(style_by_callback.get("inv:syncnom:req-42"), "primary")
        self.assertEqual(style_by_callback.get("inv:cancel:req-42"), "danger")

    def test_build_invoice_actions_can_hide_sync_button(self) -> None:
        keyboard = build_invoice_actions("req-42", allow_send=True, allow_sync=False)
        self.assertIsNotNone(keyboard)
        callbacks = {
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
        }
        self.assertNotIn("inv:syncnom:req-42", callbacks)


if __name__ == "__main__":
    unittest.main()
