from __future__ import annotations

import asyncio
import io
import sys
import tempfile
import types
import unittest
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.file_storage import PendingSplitStorage


def _install_aiogram_stubs() -> None:
    aiogram_module = types.ModuleType("aiogram")
    filters_module = types.ModuleType("aiogram.filters")
    types_module = types.ModuleType("aiogram.types")

    class _FilterField:
        def __getattr__(self, name):
            return self

    class _DispatcherRouter:
        def register(self, *args, **kwargs) -> None:
            return None

    class Bot:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class Dispatcher:
        def __init__(self, *args, **kwargs) -> None:
            self.message = _DispatcherRouter()
            self.callback_query = _DispatcherRouter()

    class Command:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class CommandStart:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class InlineKeyboardButton:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class InlineKeyboardMarkup:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class KeyboardButton:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class BotCommand:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class ReplyKeyboardMarkup:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class ReplyKeyboardRemove:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class Message:
        pass

    class CallbackQuery:
        pass

    aiogram_module.Bot = Bot
    aiogram_module.Dispatcher = Dispatcher
    aiogram_module.F = _FilterField()
    filters_module.Command = Command
    filters_module.CommandStart = CommandStart
    types_module.CallbackQuery = CallbackQuery
    types_module.InlineKeyboardButton = InlineKeyboardButton
    types_module.InlineKeyboardMarkup = InlineKeyboardMarkup
    types_module.KeyboardButton = KeyboardButton
    types_module.Message = Message
    types_module.BotCommand = BotCommand
    types_module.ReplyKeyboardMarkup = ReplyKeyboardMarkup
    types_module.ReplyKeyboardRemove = ReplyKeyboardRemove

    sys.modules["aiogram"] = aiogram_module
    sys.modules["aiogram.filters"] = filters_module
    sys.modules["aiogram.types"] = types_module


try:
    from app.bot.manager import TelegramBotManager
except ModuleNotFoundError as exc:
    if exc.name != "aiogram":
        raise
    _install_aiogram_stubs()
    from app.bot.manager import TelegramBotManager

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "smoke"


class DummyBot:
    def __init__(self, *args, **kwargs) -> None:
        self.download_payloads: list[bytes] = []
        self.sent_messages: list[dict] = []
        self.deleted_messages: list[tuple[int, int]] = []

    async def get_file(self, file_id: str):
        return SimpleNamespace(file_path=file_id)

    async def download_file(self, file_path: str):
        payload = self.download_payloads.pop(0) if self.download_payloads else b""
        return io.BytesIO(payload)

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        message = SimpleNamespace(message_id=len(self.sent_messages) + 1, chat=SimpleNamespace(id=chat_id))
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
                "message": message,
            }
        )
        return message

    async def delete_message(self, chat_id: int, message_id: int):
        self.deleted_messages.append((chat_id, message_id))

    async def set_my_commands(self, *args, **kwargs) -> None:
        return None


def _photo_message(
    *,
    user_id: int = 42,
    chat_id: int = 1001,
    media_group_id: str | None = None,
    file_id: str = "f1",
    file_size: int = 1024,
):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=chat_id),
        media_group_id=media_group_id,
        photo=[SimpleNamespace(file_id=file_id, file_size=file_size)],
        answer=AsyncMock(),
    )
    message.answer.return_value = SimpleNamespace(message_id=9000, chat=message.chat)
    return message


class BotStage5Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._bot_patcher = patch("app.bot.manager.Bot", DummyBot)
        self._bot_patcher.start()
        self.addCleanup(self._bot_patcher.stop)

        self.manager = TelegramBotManager(token="123456:TESTTOKEN", backend_url="http://localhost:8000")
        self.bot: DummyBot = self.manager.bot

        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        storage = PendingSplitStorage(Path(self._temp_dir.name) / "data")
        self.manager._storage = storage
        self.manager._split_dir = storage.split_dir
        self.manager._pending_dir = storage.pending_dir

    def test_smoke_fixtures_exist(self) -> None:
        self.assertTrue((FIXTURES_DIR / "invoice_control.txt").exists())
        self.assertTrue((FIXTURES_DIR / "receipt_control.txt").exists())
        self.assertTrue((FIXTURES_DIR / "duplicate_blob.bin").exists())

    async def test_split_album_updates_prompt_once(self) -> None:
        user_id = "42"
        group_id = "split-group-1"
        self.manager._split_users.add(user_id)
        self.bot.download_payloads = [b"image-A", b"image-B"]

        msg1 = _photo_message(user_id=42, media_group_id=group_id, file_id="photo-1")
        msg2 = _photo_message(user_id=42, media_group_id=group_id, file_id="photo-2")

        with patch("app.bot.manager.get_iiko_credentials", return_value={"login": "ok"}):
            with patch.object(self.manager, "_check_rate_limit", return_value=True):
                with patch.object(self.manager, "_update_split_prompt", new=AsyncMock()) as update_prompt:
                    await self.manager._handle_photo(msg1, msg1.photo)
                    await self.manager._handle_photo(msg2, msg2.photo)

                    task = self.manager._split_media_group_tasks.get(group_id)
                    self.assertIsNotNone(task)
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    self.manager._split_media_group_tasks.pop(group_id, None)

                    await self.manager._finalize_split_media_group(group_id, debounce_seconds=0)

                    self.assertEqual(update_prompt.await_count, 1)
                    self.assertEqual(len(self.manager._collect_split_files(user_id)), 2)

    async def test_soft_dedup_keeps_duplicate_files(self) -> None:
        user_id = "42"
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()

        first = await self.manager._store_pending_bytes("dup.bin", content, user_id)
        second = await self.manager._store_pending_bytes("dup.bin", content, user_id)
        files = self.manager._collect_pending_files(user_id)

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertEqual(len(files), 2)

    async def test_soft_dedup_sends_warning_to_user(self) -> None:
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()
        self.bot.download_payloads = [content, content]

        msg1 = _photo_message(user_id=77, file_id="photo-a")
        msg2 = _photo_message(user_id=77, file_id="photo-b")

        with patch("app.bot.manager.get_iiko_credentials", return_value={"login": "ok"}):
            with patch.object(self.manager, "_check_rate_limit", return_value=True):
                with patch.object(self.manager, "_handle_pending_choice", new=AsyncMock()):
                    await self.manager._handle_photo(msg1, msg1.photo)
                    await self.manager._handle_photo(msg2, msg2.photo)

        warning_calls = [
            call
            for call in msg2.answer.await_args_list
            if call.args and "дубликат" in str(call.args[0]).lower()
        ]
        self.assertTrue(warning_calls)


if __name__ == "__main__":
    unittest.main()
