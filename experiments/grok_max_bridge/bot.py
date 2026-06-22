"""MAX bot ↔ Grok CLI bridge."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from maxapi import Bot, Dispatcher
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters.command import Command
from maxapi.types.message import Message
from maxapi.types.updates import BotStarted, MessageCallback, MessageCreated

from experiments.grok_max_bridge.config import settings
from experiments.grok_max_bridge.keyboards import main_menu
from experiments.grok_telegram_bridge.chat_dump_hub import refresh_chat_dump
from experiments.grok_telegram_bridge.context_store import ContextStore
from experiments.grok_telegram_bridge.dashboard_hub import (
    dashboard_path,
    dashboard_summary,
    logs_summary,
    metrics_summary,
    refresh_dashboard,
    reports_summary,
)
from experiments.grok_telegram_bridge.formatter import (
    MAX_RAW_CHUNK,
    clamp_message,
    format_grok_response,
    progress_preview,
    split_message,
    wrap_code_block,
    wrap_code_block_for_max,
)
from experiments.grok_telegram_bridge.git_snapshot import capture as git_capture
from experiments.grok_telegram_bridge.grok_runner import GrokRunner, GrokRunnerError
from experiments.grok_telegram_bridge.onboarding import (
    mark_bootstrapped,
    needs_bootstrap,
    wrap_first_prompt,
)
from experiments.grok_telegram_bridge.rules_loader import load_rules_text
from experiments.grok_telegram_bridge.messages import BridgeMsg
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix
from experiments.grok_telegram_bridge.work_journal import WorkJournal

logger = logging.getLogger(__name__)

MAX_SAFE = MAX_RAW_CHUNK
MENU = [main_menu()]
HTML = ParseMode.HTML

HELP_TEXT = BridgeMsg.help_text(channel="max")


def _sender_id(event: MessageCreated | MessageCallback | BotStarted) -> int | None:
    if isinstance(event, BotStarted):
        return event.user.user_id
    if isinstance(event, MessageCallback):
        return event.callback.user.user_id
    if event.message.sender:
        return event.message.sender.user_id
    return None


class GrokMaxBridgeBot:
    def __init__(self) -> None:
        if not settings.grok_max_bridge_token:
            raise RuntimeError("GROK_MAX_BRIDGE_TOKEN is not set")
        self.allowed = settings.allowed_ids()
        self.cwd = Path(settings.grok_bridge_cwd)
        data_dir = settings.data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        self.bot = Bot(settings.grok_max_bridge_token, parse_mode=HTML)
        self.dp = Dispatcher()
        self.store = SessionStore(Path(settings.grok_max_bridge_sessions_path))
        self.context = ContextStore(data_dir / "context")
        self.journal = WorkJournal(data_dir)
        self._rules = load_rules_text(Path(settings.grok_max_bridge_rules_path))
        self._pending_check: dict[int, bool] = {}
        if self._rules:
            logger.info("Loaded bridge rules from %s", settings.grok_max_bridge_rules_path)
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
        self.dp.bot_started.register(self.on_bot_started)
        self.dp.message_created.register(self.cmd_start, Command("start"))
        self.dp.message_created.register(self.cmd_help, Command("help"))
        self.dp.message_created.register(self.cmd_new, Command("new"))
        self.dp.message_created.register(self.cmd_status, Command("status"))
        self.dp.message_created.register(self.cmd_yolo, Command("yolo"))
        self.dp.message_created.register(self.cmd_check, Command("check"))
        self.dp.message_created.register(self.cmd_check, Command("verify"))
        self.dp.message_callback.register(self.on_callback)
        self.dp.message_created.register(self.on_text)

    async def _deny_message(self, event: MessageCreated) -> None:
        await event.message.answer(BridgeMsg.ACCESS_DENIED, format=HTML)

    async def _deny_callback(self, event: MessageCallback) -> None:
        await event.ack(notification=BridgeMsg.ACCESS_DENIED)

    async def _answer_menu(self, message: Message, text: str) -> None:
        await message.answer(text, attachments=MENU, format=HTML)

    async def _callback_menu(self, event: MessageCallback, text: str) -> None:
        await event.answer(new_text=clamp_message(text), attachments=MENU, format=HTML)

    async def on_bot_started(self, event: BotStarted) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            return
        await self.bot.send_message(
            chat_id=event.chat_id,
            user_id=uid,
            text=HELP_TEXT,
            attachments=MENU,
            format=HTML,
        )

    async def cmd_start(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        await self._answer_menu(event.message, HELP_TEXT)

    async def cmd_help(self, event: MessageCreated) -> None:
        await self.cmd_start(event)

    async def cmd_new(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        self.store.clear(uid)
        self.context.clear(uid)
        await self._answer_menu(event.message, BridgeMsg.NEW_SESSION)

    async def cmd_status(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        await self._send_status_message(event.message, uid)

    async def _send_status_message(self, message: Message, uid: int) -> None:
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
        await self._answer_menu(message, "\n".join(lines))

    async def cmd_yolo(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        body = event.message.body
        text = body.text if body else ""
        parts = (text or "").split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        await self._set_yolo_message(event.message, uid, arg)

    async def _set_yolo_message(self, message: Message, uid: int, arg: str) -> None:
        sess = self.store.get(uid)
        if arg == "on":
            sess.yolo = True
        elif arg == "off":
            sess.yolo = False
        else:
            cur = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
            await self._answer_menu(message, BridgeMsg.yolo_hint(cur))
            return
        self.store.update(sess)
        await self._answer_menu(message, BridgeMsg.yolo_set(sess.yolo))

    async def cmd_check(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        body = event.message.body
        text = body.text if body else ""
        parts = (text or "").split(maxsplit=1)
        prompt = parts[1] if len(parts) > 1 else BridgeMsg.DEFAULT_CHECK_PROMPT
        await self._run_grok(event.message, uid, prompt, force_check=True)

    async def on_callback(self, event: MessageCallback) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_callback(event)
            return
        payload = (event.callback.payload or "").strip()
        if not payload.startswith("act:"):
            await event.ack(notification=BridgeMsg.CALLBACK_OK)
            return
        action = payload[4:]

        if action == "new":
            self.store.clear(uid)
            self.context.clear(uid)
            await self._callback_menu(event, "Новая сессия. Bootstrap при первом запросе.")
        elif action == "status":
            text = await self._status_text(uid)
            await self._callback_menu(event, text)
        elif action == "yolo:on":
            await self._set_yolo_callback(event, uid, "on")
        elif action == "yolo:off":
            await self._set_yolo_callback(event, uid, "off")
        elif action == "check":
            self._pending_check[uid] = True
            await self._callback_menu(
                event,
                BridgeMsg.CHECK_MODE,
            )
        elif action == "context":
            preview = self.context.format_preview(uid)
            await self._callback_menu(event, BridgeMsg.context_block(preview))
        elif action == "handoff":
            text = self.journal.handoff_text()
            chunks = split_message(text, limit=MAX_SAFE)
            await self._callback_menu(event, wrap_code_block_for_max(chunks[0]))
            for extra in chunks[1:]:
                await self._send_extra(uid, event, wrap_code_block_for_max(extra))
        elif action == "journal":
            preview = self.journal.journal_preview()
            await self._callback_menu(event, BridgeMsg.journal_block(preview))
        elif action == "dashboard":
            ok, note = await asyncio.to_thread(refresh_dashboard)
            summary = await asyncio.to_thread(dashboard_summary)
            path = dashboard_path()
            await self._callback_menu(
                event,
                BridgeMsg.dashboard_block(ok=ok, note=note, path=path, summary=summary),
            )
        elif action == "dash:refresh":
            ok, note = await asyncio.to_thread(refresh_dashboard)
            await self._callback_menu(event, BridgeMsg.dash_refresh_block(ok=ok, note=note, path=dashboard_path()))
        elif action == "metrics":
            text = await asyncio.to_thread(metrics_summary)
            await self._callback_menu(event, BridgeMsg.metrics_block(text))
        elif action == "logs":
            text = await asyncio.to_thread(logs_summary)
            chunks = split_message(text, limit=MAX_SAFE)
            await self._callback_menu(event, wrap_code_block_for_max(chunks[0]))
            for extra in chunks[1:]:
                await self._send_extra(uid, event, wrap_code_block_for_max(extra))
        elif action == "reports":
            text = await asyncio.to_thread(reports_summary)
            await self._callback_menu(
                event,
                BridgeMsg.reports_block(text, dashboard_path()),
            )
        elif action == "help":
            await self._callback_menu(event, HELP_TEXT)
        else:
            await event.ack(notification=BridgeMsg.UNKNOWN_BUTTON)

    async def _status_text(self, uid: int) -> str:
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
        return "\n".join(lines)

    async def _set_yolo_callback(self, event: MessageCallback, uid: int, arg: str) -> None:
        sess = self.store.get(uid)
        if arg == "on":
            sess.yolo = True
        elif arg == "off":
            sess.yolo = False
        self.store.update(sess)
        await self._callback_menu(event, BridgeMsg.yolo_set(sess.yolo))

    async def _send_extra(self, uid: int, event: MessageCallback, text: str) -> None:
        chat_id, _ = event.get_ids()
        await self.bot.send_message(
            chat_id=chat_id,
            user_id=uid,
            text=text,
            attachments=MENU,
            format=HTML,
        )

    async def on_text(self, event: MessageCreated) -> None:
        uid = _sender_id(event)
        if uid is None or not is_allowed(uid, self.allowed):
            await self._deny_message(event)
            return
        body = event.message.body
        text = (body.text if body else "") or ""
        text = text.strip()
        if not text or text.startswith("/"):
            return
        force_check = self._pending_check.pop(uid, False)
        await self._run_grok(event.message, uid, text, force_check=force_check)

    async def _run_grok(
        self,
        message: Message,
        user_id: int,
        prompt: str,
        *,
        force_check: bool,
    ) -> None:
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

        status_text = (
            BridgeMsg.grok_running(use_check=use_check, do_bootstrap=do_bootstrap)
        )
        sent = await message.answer(status_text, attachments=MENU, format=HTML)
        status_msg = sent.message if sent else message

        async def on_progress(text: str, phase: str) -> None:
            prefix = "💭 " if phase == "thinking" else "⏳ "
            preview = progress_preview(text)
            try:
                await status_msg.edit(
                    prefix + wrap_code_block(preview),
                    attachments=MENU,
                    format=HTML,
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
            await status_msg.edit(
                BridgeMsg.grok_error(str(exc)),
                attachments=MENU,
                format=HTML,
            )
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

        # Use Markdown→HTML conversion so **bold**, `code` etc. render properly
        await status_msg.edit(format_grok_response(first), attachments=MENU, format=HTML)
        chat_id = message.recipient.chat_id
        for extra in chunks[1:]:
            await self.bot.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=format_grok_response(extra),
                format=HTML,
            )
            await asyncio.sleep(0.3)

    async def run(self) -> None:
        await self.bot.delete_webhook()
        if self.allowed:
            logger.info("Grok MAX bridge polling started (allowed users: %s)", self.allowed)
        else:
            logger.info("Grok MAX bridge polling started (access: open — no allowlist)")
        await self.dp.start_polling(self.bot)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    bridge = GrokMaxBridgeBot()

    backoff = 5
    while True:
        try:
            await bridge.run()
            break
        except Exception as exc:
            logger.warning(
                "Bridge polling error (network to MAX?). Will retry in %ss: %s",
                backoff,
                exc,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
