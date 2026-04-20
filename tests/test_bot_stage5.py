from __future__ import annotations

import asyncio
import io
import json
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
from app.bot.messages import Msg
from app.utils.user_messages import short_request_code

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "smoke"


class DummyBot:
    def __init__(self, *args, **kwargs) -> None:
        self.download_payloads: list[bytes] = []
        self.sent_messages: list[dict] = []
        self.deleted_messages: list[tuple[int, int]] = []
        self.edited_messages: list[dict] = []
        self.pinned_messages: list[dict] = []
        self.unpinned_chats: list[int] = []

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

    async def edit_message_text(self, text: str, chat_id: int, message_id: int, reply_markup=None):
        self.edited_messages.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=chat_id))

    async def unpin_chat_message(self, chat_id: int):
        self.unpinned_chats.append(chat_id)

    async def pin_chat_message(self, chat_id: int, message_id: int, disable_notification: bool = True):
        self.pinned_messages.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "disable_notification": disable_notification,
            }
        )

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


def _document_message(
    *,
    user_id: int = 42,
    chat_id: int = 1001,
    media_group_id: str | None = None,
    file_id: str = "doc1",
):
    document = SimpleNamespace(file_id=file_id)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=chat_id),
        media_group_id=media_group_id,
        document=document,
        answer=AsyncMock(),
    )
    message.answer.return_value = SimpleNamespace(message_id=9001, chat=message.chat)
    return message, document


def _text_message(*, user_id: int = 42, chat_id: int = 1001, text: str = ""):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=chat_id),
        text=text,
        answer=AsyncMock(),
    )
    message.answer.return_value = SimpleNamespace(message_id=9002, chat=message.chat)
    return message


def _start_message(*, user_id: int = 42, chat_id: int = 1001, message_id: int = 777):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=chat_id),
        message_id=message_id,
        answer=AsyncMock(),
    )
    message.answer.return_value = SimpleNamespace(message_id=9004, chat=message.chat)
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

    async def test_auth_password_step_verifies_iiko_before_save(self) -> None:
        user_id = "42"
        self.manager._auth_state[user_id] = "await_password"
        self.manager._pending_login[user_id] = "demo_user"
        message = _text_message(user_id=42, text="demo_password")

        with patch.object(self.manager._iiko_client, "verify_credentials", new=AsyncMock(return_value=None)) as verify:
            with patch("app.bot.manager.set_iiko_credentials") as save:
                await self.manager.on_text(message)

        self.assertEqual(verify.await_count, 1)
        save.assert_called_once_with(user_id, "demo_user", "demo_password")
        self.assertNotIn(user_id, self.manager._auth_state)
        self.assertNotIn(user_id, self.manager._pending_login)
        answers = [call.args[0] for call in message.answer.await_args_list if call.args]
        self.assertIn(Msg.AUTH_CHECKING, answers)
        self.assertIn(Msg.AUTH_SAVED, answers)

    async def test_auth_password_step_returns_to_login_on_failed_verify(self) -> None:
        user_id = "42"
        self.manager._auth_state[user_id] = "await_password"
        self.manager._pending_login[user_id] = "demo_user"
        message = _text_message(user_id=42, text="bad_password")

        with patch.object(
            self.manager._iiko_client,
            "verify_credentials",
            new=AsyncMock(side_effect=RuntimeError("IIKO auth failed: status=401")),
        ) as verify:
            with patch("app.bot.manager.set_iiko_credentials") as save:
                await self.manager.on_text(message)

        self.assertEqual(verify.await_count, 1)
        save.assert_not_called()
        self.assertEqual(self.manager._auth_state.get(user_id), "await_login")
        self.assertNotIn(user_id, self.manager._pending_login)
        answers = [call.args[0] for call in message.answer.await_args_list if call.args]
        self.assertIn(Msg.AUTH_CHECKING, answers)
        self.assertIn(Msg.AUTH_FAILED, answers)

    async def test_start_with_existing_credentials_shows_switch_button(self) -> None:
        message = _start_message(user_id=42)
        with patch("app.bot.manager.get_iiko_credentials", return_value=("old_login", "old_pass")):
            await self.manager.start(message)

        message.answer.assert_awaited_once()
        self.assertEqual(message.answer.await_args.args[0], Msg.AUTH_ALREADY)
        keyboard = message.answer.await_args.kwargs.get("reply_markup")
        self.assertIsNotNone(keyboard)
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertEqual(callbacks, {"auth:switch"})

    async def test_auth_switch_callback_clears_credentials_and_requests_login(self) -> None:
        self.manager._auth_state["42"] = "await_password"
        self.manager._pending_login["42"] = "old_login"
        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            message_id=7003,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            data="auth:switch",
            answer=AsyncMock(),
        )

        with patch("app.bot.manager.clear_iiko_credentials") as clear_creds:
            await self.manager.on_mode_choice(query)

        query.answer.assert_awaited_once()
        clear_creds.assert_called_once_with("42")
        self.assertEqual(self.manager._auth_state.get("42"), "await_login")
        self.assertNotIn("42", self.manager._pending_login)
        query_message.edit_text.assert_awaited_once_with(Msg.AUTH_SWITCHED, reply_markup=None)

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

    async def test_pending_dedup_action_removes_duplicate_files(self) -> None:
        user_id = "42"
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()

        await self.manager._store_pending_bytes("dup-a.bin", content, user_id)
        await self.manager._store_pending_bytes("dup-b.bin", content, user_id)

        stats = self.manager._deduplicate_pending_dir(user_id)

        self.assertEqual(stats["removed"], 1)
        self.assertEqual(stats["kept"], 1)
        self.assertEqual(len(self.manager._collect_pending_files(user_id)), 1)

    async def test_split_dedup_button_removes_duplicates(self) -> None:
        user_id = "42"
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()
        self.manager._split_users.add(user_id)

        await self.manager._store_split_bytes("dup-a.bin", content, user_id)
        await self.manager._store_split_bytes("dup-b.bin", content, user_id)

        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query_message.answer.return_value = SimpleNamespace(message_id=7001, chat=query_message.chat)
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
        )

        with patch.object(self.manager, "_update_split_prompt", new=AsyncMock()) as update_split_prompt:
            await self.manager._handle_split_choice(query, "split:dedup")

        self.assertEqual(len(self.manager._collect_split_files(user_id)), 1)
        self.assertEqual(update_split_prompt.await_count, 1)
        self.assertTrue(query_message.edit_text.await_args_list)
        text = str(query_message.edit_text.await_args_list[0].args[0])
        self.assertIn("Удалено дубликатов: 1", text)

    async def test_pending_prompt_shows_duplicate_hint_only_when_needed(self) -> None:
        user_id = "42"
        chat_id = 1001
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()

        await self.manager._store_pending_bytes("dup-a.bin", content, user_id)
        await self.manager._store_pending_bytes("dup-b.bin", content, user_id)
        await self.manager._send_mode_keyboard_to_chat(chat_id, user_id)
        text_with_dups = self.bot.sent_messages[-1]["text"]
        self.assertIn("Найдено дубликатов: 1", text_with_dups)

        self.manager._deduplicate_pending_dir(user_id)
        await self.manager._send_mode_keyboard_to_chat(chat_id, user_id)
        text_without_dups = self.bot.sent_messages[-1]["text"]
        self.assertNotIn("Найдено дубликатов:", text_without_dups)

    async def test_split_prompt_shows_duplicate_hint_only_when_needed(self) -> None:
        user_id = "42"
        content = (FIXTURES_DIR / "duplicate_blob.bin").read_bytes()

        await self.manager._store_split_bytes("dup-a.bin", content, user_id)
        await self.manager._store_split_bytes("dup-b.bin", content, user_id)
        text_with_dups, _ = self.manager._build_split_prompt(user_id, 2)
        self.assertIn("Найдено дубликатов: 1", text_with_dups)

        self.manager._deduplicate_split_dir(user_id)
        text_without_dups, _ = self.manager._build_split_prompt(user_id, 1)
        self.assertNotIn("Найдено дубликатов:", text_without_dups)

    async def test_pdf_document_registers_pending_user_for_mode_choice(self) -> None:
        message, document = _document_message(user_id=77, file_id="pdf-file")
        self.bot.download_payloads = [b"%PDF-sample%"]

        with patch("app.bot.manager.get_iiko_credentials", return_value={"login": "ok"}):
            with patch.object(self.manager, "_check_rate_limit", return_value=True):
                with patch.object(self.manager, "_handle_pdf_mode_choice", new=AsyncMock()) as pdf_prompt:
                    await self.manager._handle_document(message, document, "invoice.pdf")

        self.assertIn("77", self.manager._pending_users)
        self.assertEqual(self.manager._pending_chats.get("77"), 1001)
        self.assertEqual(pdf_prompt.await_count, 1)

    async def test_pdf_choice_recovers_pending_state_from_saved_files(self) -> None:
        user_id = "42"
        await self.manager._store_pending_bytes("invoice.pdf", b"%PDF-sample%", user_id)

        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            answer=AsyncMock(),
        )

        with patch.object(self.manager, "_process_pending_as_batch_chat", new=AsyncMock()) as process_batch:
            with patch("app.bot.manager.set_pdf_mode") as set_mode:
                await self.manager._handle_pdf_choice(query, "pdf:fast")

        query.answer.assert_awaited_once()
        set_mode.assert_called_once_with(user_id, "fast")
        query_message.answer.assert_not_awaited()
        self.assertEqual(process_batch.await_count, 1)

    async def test_pdf_prompt_has_only_mode_buttons_and_hint(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        message.answer.return_value = SimpleNamespace(message_id=9003, chat=SimpleNamespace(id=1001))

        with patch("app.bot.manager.get_pdf_mode", return_value="fast"):
            await self.manager._handle_pdf_mode_choice(message, "42")

        self.assertTrue(message.answer.await_args_list)
        text = str(message.answer.await_args.args[0])
        self.assertIn("Если документ нечеткий, выбирайте accurate.", text)
        keyboard = message.answer.await_args.kwargs.get("reply_markup")
        self.assertIsNotNone(keyboard)
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertEqual(callbacks, {"pdf:fast", "pdf:accurate"})

    async def test_pdf_fast_choice_processes_without_continue_step(self) -> None:
        user_id = "42"
        self.manager._pending_users.add(user_id)
        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            answer=AsyncMock(),
        )

        with patch.object(self.manager, "_process_pending_as_batch_chat", new=AsyncMock()) as process_batch:
            with patch("app.bot.manager.set_pdf_mode") as set_mode:
                await self.manager._handle_pdf_choice(query, "pdf:fast")

        set_mode.assert_called_once_with(user_id, "fast")
        query.answer.assert_awaited_once()
        query_message.edit_text.assert_awaited_once_with(Msg.PDF_SET_FAST)
        self.assertEqual(process_batch.await_count, 1)

    async def test_pdf_accurate_choice_processes_without_continue_step(self) -> None:
        user_id = "42"
        self.manager._pending_users.add(user_id)
        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            answer=AsyncMock(),
        )

        with patch.object(self.manager, "_process_pending_as_batch_chat", new=AsyncMock()) as process_batch:
            with patch("app.bot.manager.set_pdf_mode") as set_mode:
                await self.manager._handle_pdf_choice(query, "pdf:accurate")

        set_mode.assert_called_once_with(user_id, "accurate")
        query.answer.assert_awaited_once()
        query_message.edit_text.assert_awaited_once_with(Msg.PDF_SET_ACCURATE)
        self.assertEqual(process_batch.await_count, 1)

    async def test_mode_merge_sends_batch_without_extra_split_step(self) -> None:
        user_id = "42"
        chat_id = 1001
        await self.manager._store_pending_bytes("part-a.bin", b"A", user_id)
        await self.manager._store_pending_bytes("part-b.bin", b"B", user_id)
        self.manager._pending_users.add(user_id)

        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            message_id=9002,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            data="mode:merge",
            answer=AsyncMock(),
        )

        with patch(
            "app.bot.manager.send_batch_to_backend",
            new=AsyncMock(return_value={"status": "queued", "request_id": "20260406_211530_123_6106711925"}),
        ) as send_batch:
            await self.manager.on_mode_choice(query)

        self.assertEqual(send_batch.await_count, 1)
        args = send_batch.await_args.args
        self.assertEqual(len(args[1]), 2)
        self.assertNotIn(user_id, self.manager._split_users)
        self.assertNotIn(user_id, self.manager._split_prompt)
        self.assertEqual(len(self.manager._collect_pending_files(user_id)), 0)

    async def test_build_status_text_includes_queue_and_last_task(self) -> None:
        user_id = "42"
        with patch("app.bot.manager.reap_stale_tasks", return_value=2):
            with patch("app.bot.manager.get_user_active_snapshot", return_value={"queued": 3, "processing": 2, "stale": 1}):
                with patch(
                    "app.bot.manager.get_user_last_task",
                    return_value={
                        "request_id": "20260408_120000_123_42",
                        "status": "processing",
                        "message": "Идет обработка",
                    },
                ):
                    text = self.manager._build_status_text(user_id)

        self.assertIn("Статус ваших заявок:", text)
        self.assertIn("Зависшие заявки: 2", text)
        self.assertIn("В очереди: 3", text)
        self.assertIn("В обработке: 2", text)
        self.assertIn("Требуют внимания: 1", text)
        self.assertIn("Последняя заявка:", text)
        self.assertIn("Состояние: обрабатывается", text)
        self.assertIn("Комментарий: Идет обработка", text)

    async def test_status_command_sends_message(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=1001),
        )
        with patch.object(self.manager, "_build_status_text", return_value="status-text") as build_status:
            await self.manager.show_status(message)

        build_status.assert_called_once_with("42")
        self.assertEqual(len(self.bot.sent_messages), 1)
        self.assertEqual(self.bot.sent_messages[0]["text"], "status-text")
        self.assertIsNotNone(self.bot.sent_messages[0]["reply_markup"])

    async def test_status_command_reuses_previous_status_message(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=1001),
        )
        with patch.object(self.manager, "_build_status_text", return_value="first-status"):
            await self.manager.show_status(message)
        with patch.object(self.manager, "_build_status_text", return_value="second-status"):
            await self.manager.show_status(message)

        self.assertEqual(len(self.bot.sent_messages), 1)
        self.assertEqual(len(self.bot.edited_messages), 1)
        self.assertEqual(self.bot.edited_messages[0]["text"], "second-status")

    async def test_status_command_pins_card_when_enabled(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=1001),
        )
        with patch("app.bot.manager.settings.status_pin_message", True):
            with patch.object(self.manager, "_build_status_text", return_value="status-text"):
                await self.manager.show_status(message)

        self.assertEqual(len(self.bot.pinned_messages), 1)
        self.assertEqual(self.bot.pinned_messages[0]["chat_id"], 1001)
        self.assertEqual(self.bot.pinned_messages[0]["message_id"], 1)

    async def test_status_refresh_callback_updates_message(self) -> None:
        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            message_id=7001,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            data="status:refresh",
            answer=AsyncMock(),
        )

        with patch.object(self.manager, "_build_status_text", return_value="status-refresh") as build_status:
            await self.manager.on_mode_choice(query)

        query.answer.assert_awaited_once()
        build_status.assert_called_once_with("42")
        query_message.edit_text.assert_awaited_once()
        self.assertEqual(query_message.edit_text.await_args.args[0], "status-refresh")
        self.assertIsNotNone(query_message.edit_text.await_args.kwargs.get("reply_markup"))

    async def test_status_retry_callback_resubmits_file(self) -> None:
        payload_dir = Path(self._temp_dir.name) / "job"
        payload_dir.mkdir(parents=True, exist_ok=True)
        source_file = payload_dir / "doc.pdf"
        source_file.write_bytes(b"pdf-bytes")
        payload_path = payload_dir / "payload.json"
        payload_path.write_text(
            '{"user_id":"42","filename":"doc.pdf","file_path":"%s","push_to_iiko":true}' % source_file.as_posix(),
            encoding="utf-8",
        )

        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            message_id=7002,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=query_message,
            data="status:retry:old_request",
            answer=AsyncMock(),
        )

        with patch.object(self.manager, "_job_payload_path", return_value=payload_path):
            with patch("app.bot.manager.send_file_to_backend", new=AsyncMock(return_value={"status": "queued", "request_id": "new_request"})) as send_file:
                with patch.object(self.manager, "_build_status_text", return_value="status-body"):
                    await self.manager.on_mode_choice(query)

        query.answer.assert_awaited_once()
        self.assertEqual(send_file.await_count, 1)
        query_message.edit_text.assert_awaited_once()
        edited_text = query_message.edit_text.await_args.args[0]
        self.assertIn("Повторно отправил документ в обработку.", edited_text)
        self.assertIn("status-body", edited_text)


    async def test_on_text_ignores_pinned_service_message(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=1001),
            text="Alice pinned a message",
            pinned_message=SimpleNamespace(message_id=555),
            answer=AsyncMock(),
        )

        await self.manager.on_text(message)

        message.answer.assert_not_awaited()

    async def test_show_final_response_keeps_send_for_import_ready(self) -> None:
        state = SimpleNamespace(
            request_id="req-42",
            payload={"parsed": {"items": []}, "iiko_uploaded": False, "iiko_import_ready": True},
            overrides={},
            items=[],
        )
        message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())

        with patch.object(self.manager, "_invoice_actions", wraps=self.manager._invoice_actions) as invoice_actions:
            await self.manager._show_final_response(message, state)

        self.assertTrue(invoice_actions.called)
        self.assertTrue(invoice_actions.call_args.kwargs.get("allow_send"))

    async def test_send_to_iiko_handles_queued_response_without_false_failure(self) -> None:
        request_id = "test_send_to_iiko_queued_42"
        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            message_id=7002,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        queued_request_id = "20260420_213427_827_6106711925"
        queued_code = short_request_code(queued_request_id) or queued_request_id

        with patch.object(self.manager, "_load_request_payload", return_value={"user_id": "42"}):
            with patch(
                "app.bot.manager.send_request_to_iiko",
                new=AsyncMock(return_value={"status": "queued", "request_id": queued_request_id}),
            ) as send_to_iiko:
                await self.manager._send_to_iiko(query_message, request_id, user_id="42")

        self.assertEqual(send_to_iiko.await_count, 1)
        self.assertTrue(query_message.edit_text.await_count >= 2)
        final_text = query_message.edit_text.await_args_list[-1].args[0]
        self.assertIn(Msg.IIKO_QUEUED.format(code_line=Msg.CODE_LINE.format(code=queued_code)).strip(), final_text)
        self.assertNotIn(request_id, self.manager._iiko_send_inflight)

    async def test_send_to_iiko_skips_when_same_request_already_inflight(self) -> None:
        request_id = "test_send_to_iiko_inflight_42"
        self.manager._iiko_send_inflight.add(request_id)
        self.addCleanup(self.manager._iiko_send_inflight.discard, request_id)

        query_message = SimpleNamespace(
            chat=SimpleNamespace(id=1001),
            message_id=7003,
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )

        with patch("app.bot.manager.send_request_to_iiko", new=AsyncMock()) as send_to_iiko:
            await self.manager._send_to_iiko(query_message, request_id, user_id="42")

        self.assertEqual(send_to_iiko.await_count, 0)
        query_message.answer.assert_awaited_once()
        text = query_message.answer.await_args.args[0]
        self.assertIn("уже выполняется", text.lower())


if __name__ == "__main__":
    unittest.main()
