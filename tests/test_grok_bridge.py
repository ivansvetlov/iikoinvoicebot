"""Unit tests for Grok Telegram bridge helpers."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.grok_telegram_bridge.formatter import split_message
from experiments.grok_telegram_bridge.grok_runner import GrokRunner
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix


class TestGrokBridge(unittest.TestCase):
    def test_split_message(self) -> None:
        chunks = split_message("a" * 5000, limit=2000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), "a" * 5000)

    def test_security(self) -> None:
        self.assertTrue(is_allowed(42, {42}))
        self.assertFalse(is_allowed(1, {42}))
        self.assertFalse(is_allowed(1, set()))

    def test_tester_triggers(self) -> None:
        self.assertTrue(should_use_check("/check fix bug", auto_check=False))
        self.assertTrue(should_use_check("implement feature", auto_check=True))
        self.assertFalse(should_use_check("hello", auto_check=False))
        self.assertEqual(strip_check_prefix("/check do x"), "do x")

    def test_session_store_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            store.touch_prompt(99, "sess-abc")
            sess = store.get(99)
            self.assertEqual(sess.grok_session_id, "sess-abc")
            self.assertEqual(sess.message_count, 1)
            store.clear(99)
            self.assertIsNone(store.get(99).grok_session_id)

    def test_grok_cmd_build(self) -> None:
        runner = GrokRunner(
            cli_path=Path("grok.exe"),
            cwd=Path("."),
            model="grok-build",
            max_turns=10,
            timeout_sec=60,
            yolo=True,
            stream=True,
        )
        cmd = runner._build_cmd("hi", session_id="abc", use_check=True)
        self.assertIn("--resume", cmd)
        self.assertIn("abc", cmd)
        self.assertIn("--check", cmd)
        self.assertIn("--always-approve", cmd)
        self.assertIn("streaming-json", cmd)

    def test_grok_cmd_rules(self) -> None:
        runner = GrokRunner(
            cli_path=Path("grok.exe"),
            cwd=Path("."),
            model="grok-build",
            max_turns=10,
            timeout_sec=60,
            yolo=False,
            stream=False,
            rules_text="# metaprompt",
        )
        cmd = runner._build_cmd("hi", session_id=None, use_check=False)
        self.assertIn("--rules", cmd)
        self.assertIn("# metaprompt", cmd)

    def test_stream_parser(self) -> None:
        lines = [
            '{"type":"text","data":"Hel"}',
            '{"type":"text","data":"lo"}',
            '{"type":"end","stopReason":"EndTurn","sessionId":"sess-1"}',
        ]
        result = GrokRunner.parse_stream_lines(lines)
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.session_id, "sess-1")
        self.assertEqual(result.stop_reason, "EndTurn")


if __name__ == "__main__":
    unittest.main()
