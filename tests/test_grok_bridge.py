"""Unit tests for Grok Telegram bridge helpers."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.grok_telegram_bridge.context_store import ContextStore
from experiments.grok_telegram_bridge.formatter import format_grok_for_max, format_grok_response, split_message
from experiments.grok_telegram_bridge.grok_runner import GrokRunner
from experiments.grok_telegram_bridge.keyboards import main_menu
from experiments.grok_telegram_bridge.messages import BridgeMsg
from experiments.grok_telegram_bridge.onboarding import needs_bootstrap, wrap_first_prompt
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix
from experiments.grok_telegram_bridge.work_journal import WorkJournal
from experiments.grok_telegram_bridge.git_snapshot import GitSnapshot


class TestGrokBridge(unittest.TestCase):
    def test_format_grok_max_markdown_passthrough(self) -> None:
        raw = "Это **тестовый жирный** текст."
        self.assertEqual(format_grok_for_max(raw), raw)
        self.assertEqual(format_grok_response(raw), "Это <b>тестовый жирный</b> текст.")

    def test_split_message(self) -> None:
        chunks = split_message("a" * 5000, limit=2000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), "a" * 5000)

    def test_bridge_messages(self) -> None:
        tg = BridgeMsg.help_text(channel="telegram")
        mx = BridgeMsg.help_text(channel="max")
        self.assertIn("grok_bridge", tg)
        self.assertIn("grok_max_bridge", mx)
        self.assertIn("check", BridgeMsg.CHECK_MODE)
        self.assertIn("/help", mx)
        self.assertIn("ограничение платформы", mx)
        self.assertIn("/new", BridgeMsg.commands_text(channel="telegram"))
        self.assertIn("Неизвестная команда", BridgeMsg.unknown_command("foo"))

    def test_security(self) -> None:
        self.assertTrue(is_allowed(42, {42}))
        self.assertFalse(is_allowed(1, {42}))
        self.assertTrue(is_allowed(999, set()))

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
            self.assertIn("👤", preview)
            self.assertIn("🤖", preview)
            self.assertIn("hello", preview)

    def test_work_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            journal = WorkJournal(Path(tmp))
            snap = GitSnapshot(branch="main", status_short=" M a.py", dirty_count=2, diff_stat="2 files")
            started = finished = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            journal.record_run(
                user_id=42,
                run_id="run-1",
                started_at=started,
                finished_at=finished,
                prompt="Настроить Tailscale для дашборда",
                response="Готово. Следующий шаг: проверить firewall.",
                grok_session_id=None,
                stop_reason=None,
                use_check=False,
                git_before=snap,
                git_after=snap,
                cwd=Path(tmp),
            )
            summary = journal.work_summary(42)
            self.assertIn("Что делали", summary)
            self.assertIn("Tailscale", summary)
            self.assertIn("Пока не закрыто", summary)

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
        flat = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("act:dashboard", flat)
        self.assertIn("act:handoff", flat)
        self.assertNotIn("act:logs", flat)
        self.assertNotIn("act:dash:refresh", flat)
        self.assertGreaterEqual(len(flat), 8)

    def test_dashboard_data(self) -> None:
        from scripts.dashboard_data import collect_all

        dash = collect_all(metrics_hours=24)
        self.assertIn("logs", dash)
        self.assertIn("metrics", dash)
        self.assertIn("online", dash)
        self.assertIn("availability_html", dash)

    def test_dashboard_refresh(self) -> None:
        from experiments.grok_telegram_bridge.dashboard_hub import refresh_dashboard

        ok, _msg = refresh_dashboard()
        self.assertTrue(ok)
        self.assertTrue(Path("docs/assets/project-dashboard.html").exists())

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
