"""Telegram bot ↔ Grok CLI bridge."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from experiments.grok_telegram_bridge.config import settings
from experiments.grok_telegram_bridge.formatter import progress_preview, split_message, wrap_code_block
from experiments.grok_telegram_bridge.grok_runner import GrokRunner, GrokRunnerError
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.grok_telegram_bridge.session_store import SessionStore
from experiments.grok_telegram_bridge.tester import should_use_check, strip_check_prefix

logger = logging.getLogger(__name__)

HELP_TEXT = """\
<b>Grok Bridge</b> — удалённый терминальный агент на твоём ПК.

<b>Команды</b>
/start — это сообщение
/new — новая сессия Grok (сброс контекста)
/status — session id, cwd, режим
/yolo on|off — авто-approve инструментов (как --always-approve в CLI)
/check &lt;текст&gt; — запрос + тестировщик (--check / check-work)

<b>Обычный текст</b> → <code>grok -p</code> headless с <code>--resume</code>.

Поведение максимально близко к CLI: тот же cwd, те же tools, streaming в одно сообщение.
"""


class GrokBridgeBot:
    def __init__(self) -> None:
        if not settings.grok_bridge_bot_token:
            raise RuntimeError("GROK_BRIDGE_BOT_TOKEN is not set")
        self.allowed = settings.allowed_ids()
        if not self.allowed:
            raise RuntimeError("GROK_BRIDGE_ALLOWED_USER_IDS is empty")

        self.bot = Bot(token=settings.grok_bridge_bot_token)
        self.dp = Dispatcher()
        self.store = SessionStore(Path(settings.grok_bridge_sessions_path))
        self._register()

    def _runner_for(self, user_id: int) -> GrokRunner:
        sess = self.store.get(user_id)
        yolo = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
        return GrokRunner(
            cli_path=Path(settings.grok_cli_path),
            cwd=Path(settings.grok_bridge_cwd),
            model=settings.grok_bridge_model,
            max_turns=settings.grok_bridge_max_turns,
            timeout_sec=settings.grok_bridge_timeout_sec,
            yolo=yolo,
            stream=settings.grok_bridge_stream,
        )

    def _register(self) -> None:
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_new, Command("new"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_yolo, Command("yolo"))
        self.dp.message.register(self.cmd_check, Command("check"))
        self.dp.message.register(self.cmd_check, Command("verify"))
        self.dp.message.register(self.on_text, F.text)

    async def _deny(self, message: Message) -> None:
        await message.answer("Access denied.")

    async def cmd_start(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        await message.answer(HELP_TEXT, parse_mode=ParseMode.HTML)

    async def cmd_help(self, message: Message) -> None:
        await self.cmd_start(message)

    async def cmd_new(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        self.store.clear(message.from_user.id)
        await message.answer("Новая сессия Grok. Контекст сброшен.")

    async def cmd_status(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        sess = self.store.get(message.from_user.id)
        yolo = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
        lines = [
            f"<b>cwd</b>: <code>{settings.grok_bridge_cwd}</code>",
            f"<b>model</b>: <code>{settings.grok_bridge_model}</code>",
            f"<b>grok session</b>: <code>{sess.grok_session_id or '(new)'}</code>",
            f"<b>messages</b>: {sess.message_count}",
            f"<b>yolo</b>: {yolo}",
            f"<b>stream</b>: {settings.grok_bridge_stream}",
            f"<b>auto-check</b>: {settings.grok_bridge_auto_check}",
        ]
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_yolo(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        parts = (message.text or "").split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        sess = self.store.get(message.from_user.id)
        if arg == "on":
            sess.yolo = True
        elif arg == "off":
            sess.yolo = False
        else:
            cur = settings.grok_bridge_yolo if sess.yolo is None else sess.yolo
            await message.answer(f"YOLO сейчас: <b>{cur}</b>. /yolo on | /yolo off", parse_mode=ParseMode.HTML)
            return
        self.store.update(sess)
        await message.answer(f"YOLO: <b>{sess.yolo}</b>", parse_mode=ParseMode.HTML)

    async def cmd_check(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        prompt = (message.text or "").split(maxsplit=1)
        text = prompt[1] if len(prompt) > 1 else "Проверь последние изменения в проекте."
        await self._run_grok(message, text, force_check=True)

    async def on_text(self, message: Message) -> None:
        if not message.from_user or not is_allowed(message.from_user.id, self.allowed):
            await self._deny(message)
            return
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return
        await self._run_grok(message, text, force_check=False)

    async def _run_grok(self, message: Message, prompt: str, *, force_check: bool) -> None:
        user_id = message.from_user.id  # type: ignore[union-attr]
        sess = self.store.get(user_id)
        runner = self._runner_for(user_id)

        use_check = force_check or should_use_check(prompt, auto_check=settings.grok_bridge_auto_check)
        prompt = strip_check_prefix(prompt)

        status = await message.answer(
            "⏳ Grok…" + (" + тестировщик (--check)" if use_check else ""),
            parse_mode=ParseMode.HTML,
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
            await status.edit_text(f"❌ <b>Grok error</b>\n<pre>{exc}</pre>", parse_mode=ParseMode.HTML)
            return

        self.store.touch_prompt(user_id, result.session_id)

        footer = []
        if result.session_id:
            footer.append(f"session: {result.session_id[:8]}…")
        if use_check:
            footer.append("check: on")
        if result.stop_reason:
            footer.append(f"stop: {result.stop_reason}")

        body = result.text or "(пустой ответ)"
        chunks = split_message(body)
        first = chunks[0]
        if footer:
            first += "\n\n— " + " · ".join(footer)

        await status.edit_text(wrap_code_block(first), parse_mode=ParseMode.HTML)
        for extra in chunks[1:]:
            await message.answer(wrap_code_block(extra), parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)

    async def run(self) -> None:
        logger.info("Grok bridge polling started (allowed users: %s)", self.allowed)
        await self.dp.start_polling(self.bot)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    bridge = GrokBridgeBot()
    await bridge.run()
