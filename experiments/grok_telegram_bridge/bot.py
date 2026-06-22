"""Telegram bot ↔ Grok CLI bridge."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from experiments.grok_telegram_bridge.config import settings
from experiments.grok_telegram_bridge.context_store import ContextStore
from experiments.grok_telegram_bridge.formatter import (
    format_grok_response,
    progress_preview,
    split_message,
    wrap_code_block,
)
from experiments.grok_telegram_bridge.git_snapshot import capture as git_capture
from experiments.grok_telegram_bridge.grok_runner import GrokRunner, GrokRunnerError
from experiments.grok_telegram_bridge.keyboards import main_menu
from experiments.grok_telegram_bridge.messages import BridgeMsg
from experiments.grok_telegram_bridge.onboarding import (
    mark_bootstrapped,
    needs_bootstrap,
    wrap_first_prompt,
)
from experiments.grok_telegram_bridge.rules_loader import load_rules_text
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix
from experiments.grok_telegram_bridge.chat_dump_hub import refresh_chat_dump
from experiments.grok_telegram_bridge.dashboard_hub import (
    dashboard_path,
    dashboard_summary,
    logs_summary,
    metrics_summary,
    refresh_dashboard,
    reports_summary,
)
from experiments.grok_telegram_bridge.work_journal import WorkJournal

logger = logging.getLogger(__name__)

HELP_TEXT = BridgeMsg.help_text(channel="telegram")


class GrokBridgeBot:
    def __init__(self) -> None:
        if not settings.grok_bridge_bot_token:
            raise RuntimeError("GROK_BRIDGE_BOT_TOKEN is not set")
        self.allowed = settings.allowed_ids()
        self.cwd = Path(settings.grok_bridge_cwd)
        data_dir = settings.data_dir()

        proxy = (settings.grok_bridge_proxy or "").strip() or None
        if proxy:
            session = AiohttpSession(proxy=proxy)
            self.bot = Bot(token=settings.grok_bridge_bot_token, session=session)
            logger.info("Bridge using proxy for Telegram: %s", proxy)
        else:
            self.bot = Bot(token=settings.grok_bridge_bot_token)
        self.dp = Dispatcher()
        self.store = SessionStore(Path(settings.grok_bridge_sessions_path))
        self.context = ContextStore(data_dir / "context")
        self.journal = WorkJournal(data_dir)
        self._rules = load_rules_text(Path(settings.grok_bridge_rules_path))
        self._pending_check: dict[int, bool] = {}
        if self._rules:
            logger.info("Loaded bridge rules from %s", settings.grok_bridge_rules_path)
        self._register()

    def _runner_for(self, user_id: int) -> GrokRunner:
        sess = self.store.get(user_id)
        yolo = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
        return GrokRunner(
            cli_path=Path(settings.grok_cli_path),
            cwd=self.cwd,
            model=settings.grok_bridge_model,
            max_turns=settings.grok_bridge_max_turns,
            timeout_sec=settings.grok_bridge_timeout_sec,
            yolo=yolo,
            stream=settings.grok_bridge_stream,
            rules_text=self._rules,
        )

    def _register(self) -> None:
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_new, Command("new"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_yolo, Command("yolo"))
        self.dp.message.register(self.cmd_check, Command("check"))
        self.dp.message.register(self.cmd_check, Command("verify"))
        self.dp.callback_query.register(self.on_callback)
        self.dp.message.register(self.on_text, F.text)

    async def _deny(self, message: Message) -> None:
        await message.answer(BridgeMsg.ACCESS_DENIED)

    async def _reply_menu(self, message: Message, text: str) -> None:
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())

    async def cmd_start(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        await self._reply_menu(message, HELP_TEXT)

    async def cmd_help(self, message: Message) -> None:
        await self.cmd_start(message)

    async def cmd_new(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        uid = message.from_user.id
        self.store.clear(uid)
        self.context.clear(uid)
        await self._reply_menu(message, BridgeMsg.NEW_SESSION)

    async def cmd_status(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        await self._send_status(message)

    async def _send_status(self, message: Message) -> None:
        uid = message.from_user.id  # type: ignore[union-attr]
        sess = self.store.get(uid)
        yolo = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
        git = git_capture(self.cwd)
        lines = BridgeMsg.status_lines(
            cwd=settings.grok_bridge_cwd,
            git=git,
            model=settings.grok_bridge_model,
            sess=sess,
            yolo=yolo,
            has_rules=bool(self._rules),
        )
        await self._reply_menu(message, "\n".join(lines))

    async def cmd_yolo(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        parts = (message.text or "").split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        await self._set_yolo(message, arg)

    async def _set_yolo(self, message: Message, arg: str) -> None:
        uid = message.from_user.id  # type: ignore[union-attr]
        sess = self.store.get(uid)
        if arg == "on":
            sess.yolo = True
        elif arg == "off":
            sess.yolo = False
        else:
            cur = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
            await self._reply_menu(message, BridgeMsg.yolo_hint(cur))
            return
        self.store.update(sess)
        await self._reply_menu(message, BridgeMsg.yolo_set(sess.yolo))

    async def cmd_check(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        prompt = (message.text or "").split(maxsplit=1)
        text = prompt[1] if len(prompt) > 1 else BridgeMsg.DEFAULT_CHECK_PROMPT
        await self._run_grok(message, text, force_check=True)

    async def on_callback(self, query: CallbackQuery) -> None:
        if not query.from_user or not is_allowed(query.from_user.id, self.allowed):
            await query.answer(BridgeMsg.ACCESS_DENIED, show_alert=True)
            return
        data = (query.data or "").strip()
        if not data.startswith("act:"):
            await query.answer()
            return
        action = data[4:]
        msg = query.message
        if not msg:
            await query.answer()
            return
        await query.answer()

        if action == "new":
            self.store.clear(query.from_user.id)
            self.context.clear(query.from_user.id)
            await self._reply_menu(msg, "Новая сессия. Bootstrap при первом запросе.")
        elif action == "status":
            await self._send_status(msg)
        elif action == "yolo:on":
            await self._set_yolo(msg, "on")
        elif action == "yolo:off":
            await self._set_yolo(msg, "off")
        elif action == "check":
            self._pending_check[query.from_user.id] = True
            await self._reply_menu(
                msg,
                BridgeMsg.CHECK_MODE,
            )
        elif action == "context":
            preview = self.context.format_preview(query.from_user.id)
            await self._reply_menu(msg, BridgeMsg.context_block(preview))
        elif action == "handoff":
            text = self.journal.handoff_text()
            chunks = split_message(text, limit=3800)
            await msg.answer(wrap_code_block(chunks[0]), parse_mode=ParseMode.HTML, reply_markup=main_menu())
            for extra in chunks[1:]:
                await msg.answer(wrap_code_block(extra), parse_mode=ParseMode.HTML)
        elif action == "journal":
            preview = self.journal.journal_preview()
            await self._reply_menu(msg, BridgeMsg.journal_block(preview))
        elif action == "dashboard":
            ok, note = await asyncio.to_thread(refresh_dashboard)
            summary = await asyncio.to_thread(dashboard_summary)
            path = dashboard_path()
            await self._reply_menu(
                msg,
                BridgeMsg.dashboard_block(ok=ok, note=note, path=path, summary=summary),
            )
        elif action == "dash:refresh":
            ok, note = await asyncio.to_thread(refresh_dashboard)
            await self._reply_menu(msg, BridgeMsg.dash_refresh_block(ok=ok, note=note, path=dashboard_path()))
        elif action == "metrics":
            text = await asyncio.to_thread(metrics_summary)
            await self._reply_menu(msg, BridgeMsg.metrics_block(text))
        elif action == "logs":
            text = await asyncio.to_thread(logs_summary)
            for chunk in split_message(text, limit=3800):
                await msg.answer(wrap_code_block(chunk), parse_mode=ParseMode.HTML, reply_markup=main_menu())
        elif action == "reports":
            text = await asyncio.to_thread(reports_summary)
            await self._reply_menu(
                msg,
                BridgeMsg.reports_block(text, dashboard_path()),
            )
        elif action == "help":
            await self._reply_menu(msg, HELP_TEXT)

    async def on_text(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return
        force_check = self._pending_check.pop(message.from_user.id, False)
        await self._run_grok(message, text, force_check=force_check)

    async def _run_grok(self, message: Message, prompt: str, *, force_check: bool) -> None:
        user_id = message.from_user.id  # type: ignore[union-attr]
        sess = self.store.get(user_id)
        runner = self._runner_for(user_id)

        use_check = force_check or should_use_check(prompt, auto_check=settings.grok_bridge_auto_check)
        prompt = strip_check_prefix(prompt)

        do_bootstrap = needs_bootstrap(sess.meta)
        if do_bootstrap:
            prompt = wrap_first_prompt(prompt, bootstrap=True)

        run_id = self.journal.new_run_id()
        started = datetime.now(timezone.utc)
        git_before = git_capture(self.cwd)

        self.context.append(user_id, role="user", text=prompt, run_id=run_id)

        status = await message.answer(
            BridgeMsg.grok_running(use_check=use_check, do_bootstrap=do_bootstrap),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )

        async def on_progress(text: str, phase: str) -> None:
            prefix = "💭 " if phase == "thinking" else "⏳ "
            preview = progress_preview(text)
            try:
                await status.edit_text(
                    prefix + wrap_code_block(preview),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:  # noqa: BLE001
                pass

        try:
            result = await runner.run(
                prompt,
                session_id=sess.grok_session_id,
                use_check=use_check,
                on_progress=on_progress if settings.grok_bridge_stream else None,
            )
        except GrokRunnerError as exc:
            logger.exception("Grok failed for user %s", user_id)
            await status.edit_text(BridgeMsg.grok_error(str(exc)), parse_mode=ParseMode.HTML)
            return

        finished = datetime.now(timezone.utc)
        git_after = git_capture(self.cwd)
        body = result.text or BridgeMsg.EMPTY_RESPONSE

        if do_bootstrap:
            sess.meta = mark_bootstrapped(sess.meta)
        self.store.touch_prompt(user_id, result.session_id)
        if do_bootstrap:
            updated = self.store.get(user_id)
            updated.meta = sess.meta
            self.store.update(updated)

        self.context.append(
            user_id,
            role="assistant",
            text=body,
            run_id=run_id,
            grok_session_id=result.session_id,
        )
        asyncio.create_task(asyncio.to_thread(refresh_dashboard))
        asyncio.create_task(asyncio.to_thread(refresh_chat_dump, self.cwd))

        self.journal.record_run(
            user_id=user_id,
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            prompt=prompt,
            response=body,
            grok_session_id=result.session_id,
            stop_reason=result.stop_reason,
            use_check=use_check,
            git_before=git_before,
            git_after=git_after,
            cwd=self.cwd,
        )

        footer = [f"run: {run_id[:20]}…"]
        if result.session_id:
            footer.append(f"session: {result.session_id[:8]}…")
        if use_check:
            footer.append("check: on")
        if do_bootstrap:
            footer.append("bootstrap: done")

        chunks = split_message(body)
        first = chunks[0]
        if footer:
            first += "\n\n— " + " · ".join(footer)

        # Use Markdown→HTML conversion so **bold**, `code` etc. render
        await status.edit_text(format_grok_response(first), parse_mode=ParseMode.HTML, reply_markup=main_menu())
        for extra in chunks[1:]:
            await message.answer(format_grok_response(extra), parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)

    async def run(self) -> None:
        if self.allowed:
            logger.info("Grok bridge polling started (allowed users: %s)", self.allowed)
        else:
            logger.info("Grok bridge polling started (access: open — no allowlist)")
        await self.dp.start_polling(self.bot)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    bridge = GrokBridgeBot()

    # Resilient wrapper: transient network problems (common on this machine with multiple VPNs)
    # should not kill the whole bridge process. Keep retrying.
    backoff = 5
    while True:
        try:
            await bridge.run()
            break  # normal exit
        except Exception as exc:
            logger.warning(
                "Bridge polling error (network to Telegram?). Will retry in %ss: %s",
                backoff, exc
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
