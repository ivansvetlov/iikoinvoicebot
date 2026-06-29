"""Smoke tests for channel-neutral invoice bot contracts."""

import unittest

from app.bot.invoice_keyboards import build_invoice_actions
from app.channels.protocol import IncomingEvent, IncomingKind, OutgoingAction, OutgoingMessage


class ChannelProtocolTests(unittest.TestCase):
    def test_invoice_keyboard_is_channel_neutral_dict(self) -> None:
        kb = build_invoice_actions("req-123")
        self.assertIsNotNone(kb)
        assert kb is not None
        self.assertIn("inline_keyboard", kb)
        payloads = [
            btn["callback_data"]
            for row in kb["inline_keyboard"]
            for btn in row
        ]
        self.assertTrue(any(p.startswith("inv:") for p in payloads))

    def test_incoming_event_dataclass(self) -> None:
        ev = IncomingEvent(
            kind=IncomingKind.COMMAND,
            user_id="42",
            channel="max",  # type: ignore[arg-type]
            command="start",
        )
        self.assertEqual(ev.command, "start")

    def test_outgoing_action_send(self) -> None:
        action = OutgoingAction(send=OutgoingMessage(text="ok"))
        self.assertEqual(action.send.text, "ok")


if __name__ == "__main__":
    unittest.main()
