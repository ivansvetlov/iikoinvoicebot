"""Unit tests for Grok Telegram bridge helpers."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.grok_telegram_bridge.context_store import ContextStore
from experiments.grok_telegram_bridge.formatter import split_message
from experiments.grok_telegram_bridge.grok_runner import GrokRunner
from experiments.grok_telegram_bridge.keyboards import main_menu
from experiments.grok_telegram_bridge.onboarding import needs_bootstrap, wrap_first_prompt
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix
from experiments.grok_telegram_bridge.work_journal import WorkJournal
from experiments.grok_telegram_bridge.git_snapshot import GitSnapshot


class TestGrokBridge(unittest.TestCase):
    def test_split_message(self) -> None:
        chunks = split_message("a" * 5000, limit=2000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), "a" * 5000)

    def test_security(self) -> None:
        self.assertTrue(is_allowed(42, {42}))
        self.assertFalse(is_allowed(1, {42}))

    def test_tester_triggers(self) -> None:
        self.assertTrue(should_use_check("/check fix bug", auto_check=False))
        self.assertFalse(should_use_check("hello", auto_check=False))
        self.assertEqual(strip_check_prefix("/check do x"), "do x")

    def test_session_meta(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            store.touch_prompt(1, "s1", meta={"bootstrap_done": True})
            sess = store.get(1)
            self.assertTrue(sess.meta.get("bootstrap_done"))

    def test_onboarding(self) -> None:
        self.assertTrue(needs_bootstrap({}))
        self.assertFalse(needs_bootstrap({"bootstrap_done": True}))
        wrapped = wrap_first_prompt("fix bug", bootstrap=True)
        self.assertIn("Bootstrap", wrapped)
        self.assertIn("fix bug", wrapped)

    def test_context_store(self) -> None:
        with TemporaryDirectory() as tmp:
            ctx = ContextStore(Path(tmp), max_turns=5)
            ctx.append(7, role="user", text="hello")
            ctx.append(7, role="assistant", text="world")
            preview = ctx.format_preview(7)
            self.assertIn("[user]", preview)
            self.assertIn("[assistant]", preview)

    def test_journal_record(self) -> None:
        with TemporaryDirectory() as tmp:
            journal = WorkJournal(Path(tmp))
            run_id = journal.new_run_id()
            snap = GitSnapshot(branch="main", status_short="", diff_stat="", dirty_count=0)
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            rec = journal.record_run(
                user_id=1,
                run_id=run_id,
                started_at=now,
                finished_at=now,
                prompt="ping",
                response="pong",
                grok_session_id="sess",
                stop_reason="EndTurn",
                use_check=False,
                git_before=snap,
                git_after=snap,
                cwd=Path(tmp),
            )
            self.assertEqual(rec.prompt_preview, "ping")
            self.assertTrue((Path(tmp) / "HANDOFF_LATEST.md").exists())
            self.assertTrue((Path(tmp) / "runs" / run_id / "response.txt").exists())

    def test_grok_cmd_build(self) -> None:
        runner = GrokRunner(
            cli_path=Path("grok.exe"),
            cwd=Path("."),
            model="grok-build",
            max_turns=10,
            timeout_sec=60,
            yolo=True,
            stream=True,
            rules_text="# rules",
        )
        cmd = runner._build_cmd("hi", session_id="abc", use_check=True)
        self.assertIn("--resume", cmd)
        self.assertIn("--rules", cmd)
        self.assertIn("--always-approve", cmd)

    def test_keyboards(self) -> None:
        kb = main_menu()
        self.assertGreaterEqual(len(kb.inline_keyboard), 4)

    def test_todo_html_parser(self) -> None:
        from scripts.render_todo_dashboard import parse_todo

        sample = Path("docs/planning/TODO.md")
        if sample.exists():
            sections = parse_todo(sample)
            self.assertGreater(len(sections), 3)
            with_checkboxes = [s for s in sections if s.checkbox_total > 0]
            self.assertGreater(len(with_checkboxes), 0)


if __name__ == "__main__":
    unittest.main()
