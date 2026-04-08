"""Модуль управления Telegram-ботом и его обработчиками."""

import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    BotCommand,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.bot.backend_client import send_batch_to_backend, send_file_to_backend
from app.bot.event_codes import BOT_BACKEND_UNAVAILABLE, BOT_NO_PENDING, BOT_RATE_LIMIT, event_meta, with_event_code
from app.bot.file_storage import PendingSplitStorage
from app.bot.messages import Msg
from app.config import settings
from app.services.user_store import (
    get_iiko_credentials,
    get_pdf_mode,
    set_iiko_credentials,
    set_pdf_mode,
)
from app.utils.user_messages import format_user_response, format_invoice_markdown, short_request_code

if TYPE_CHECKING:
    from app.bot.manager import EditState

logger = logging.getLogger(__name__)

STATUS_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "mailbox"
STATUS_LOG_DIR.mkdir(parents=True, exist_ok=True)


class TelegramBotManager:
    """Инкапсулирует логику Telegram-бота и обработку сообщений."""

    def __init__(self, token: str, backend_url: str) -> None:
        self._backend_url = backend_url.rstrip("/")
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self._register_handlers()
        self._auth_state: dict[str, str] = {}
        self._pending_login: dict[str, str] = {}
        base_data_dir = Path(__file__).resolve().parents[2] / "data"
        self._storage = PendingSplitStorage(base_data_dir=base_data_dir)
        # Сохраняем директории для обратной совместимости и простоты отладки
        self._split_dir = self._storage.split_dir
        self._pending_dir = self._storage.pending_dir

        self._split_users: set[str] = set()
        self._pending_users: set[str] = set()
        self._pending_tasks: dict[str, asyncio.Task] = {}
        self._pending_chats: dict[str, int] = {}
        self._pending_prompt: dict[str, int] = {}
        self._split_prompt: dict[str, int] = {}
        self._media_groups: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task] = {}
        self._split_media_groups: dict[str, dict] = {}
        self._split_media_group_tasks: dict[str, asyncio.Task] = {}
        self._rate_limits: dict[str, list[datetime]] = {}
        self._recent_hashes: dict[str, dict[str, datetime]] = {}
        self._edit_state: dict[str, EditState] = {}
        logger.info("Bot manager initialized")
        self._storage.cleanup_old()

    async def run(self) -> None:
        """Запускает polling-цикл бота."""
        logger.info("Starting bot polling")
        logger.info("✅ Bot ready, polling started")
        await self._set_visible_commands()
        await self.dp.start_polling(self.bot)

    async def _set_visible_commands(self) -> None:
        """Оставляем в списке команд только /start."""
        try:
            await self.bot.set_my_commands(
                [
                    BotCommand(command="start", description=Msg.CMD_START_DESC),
                ]
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to set bot commands")

    def _register_handlers(self) -> None:
        """Регистрирует обработчики сообщений."""
        self.dp.message.register(self.start, CommandStart())

        self.dp.message.register(self.start_split, Command("split"))
        self.dp.message.register(self.finish_split, Command("done"))
        self.dp.message.register(self.cancel_split, Command("cancel"))

        # выбор режима обработки ожидающих файлов (объединить/раздельно)
        self.dp.callback_query.register(self.on_mode_choice)
        self.dp.message.register(self.on_reply_to_file, F.reply_to_message)
        self.dp.message.register(self.on_text, F.text)
        self.dp.message.register(self.on_document, F.document)
        self.dp.message.register(self.on_photo, F.photo)
        self.dp.message.register(self.on_unsupported_message)

    async def start(self, message: Message) -> None:
        """Отправляет приветствие и запускает авторизацию в iiko."""
        logger.info("/start from user_id=%s", message.from_user.id if message.from_user else "unknown")
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        self._reset_user_buffers(user_id)
        if get_iiko_credentials(user_id):
            await message.answer(Msg.AUTH_ALREADY)
            return
        await message.answer(Msg.AUTH_START)
        self._auth_state[user_id] = "await_login"
        self._log_status(user_id, "auth_requested", {"message_id": message.message_id})

    async def on_text(self, message: Message) -> None:
        """Обрабатывает текстовые сообщения для авторизации."""
        if not message.from_user:
            return

        user_id = str(message.from_user.id)
        if await self._handle_edit_text(message, user_id):
            return
        if user_id in self._pending_users:
            text = (message.text or "").strip().lower()
            if text in Msg.MERGE_ALIASES:
                await self._accept_pending_as_split(message, user_id)
                self._log_status(user_id, "mode_selected", {"mode": "merge"})
                return

        state = self._auth_state.get(user_id)
        if not state:
            await message.answer(Msg.ACCEPTS_FILES)
            return

        text = (message.text or "").strip()
        if not text:
            return

        if state == "await_login":
            self._pending_login[user_id] = text
            self._auth_state[user_id] = "await_password"
            await message.answer(Msg.AUTH_PASSWORD)
            self._log_status(user_id, "auth_login_received")
            return

        if state == "await_password":
            login = self._pending_login.get(user_id)
            if not login:
                self._auth_state[user_id] = "await_login"
                await message.answer(Msg.AUTH_LOGIN_MISSING)
                return
            set_iiko_credentials(user_id, login, text)
            self._auth_state.pop(user_id, None)
            self._pending_login.pop(user_id, None)
            await message.answer(Msg.AUTH_SAVED)
            self._log_status(user_id, "auth_completed")
            return
        await message.answer(Msg.ACCEPTS_FILES)

    async def start_split(self, message: Message) -> None:
        """Включает режим сплит для объединения нескольких файлов в одну накладную."""
        if not message.from_user:
            return
        if not settings.enable_split_mode:
            await message.answer(Msg.SPLIT_DISABLED)
            return
        user_id = str(message.from_user.id)
        if not get_iiko_credentials(user_id):
            await message.answer(Msg.NO_IIKO_CREDENTIALS)
            return
        self._split_users.add(user_id)
        self._clear_split_dir(user_id)
        self._clear_split_media_groups(user_id)
        # На старте split очищаем pending, чтобы не смешивать режимы.
        self._clear_pending_dir(user_id)
        self._pending_users.discard(user_id)
        self._pending_tasks.pop(user_id, None)
        self._pending_prompt.pop(user_id, None)

        await message.answer(
            Msg.SPLIT_ENABLED,
            reply_markup=ReplyKeyboardRemove(),
        )
        self._log_status(user_id, "split_started")

    async def finish_split(self, message: Message) -> None:
        """Завершает режим сплит и отправляет все части на обработку."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        if user_id not in self._split_users:
            await message.answer(Msg.SPLIT_NOT_ENABLED)
            return
        await message.answer(Msg.SPLIT_FINISHING, reply_markup=ReplyKeyboardRemove())
        await self._finalize_split(message.chat.id, user_id, status_message=None)

    async def cancel_split(self, message: Message) -> None:
        """Отменяет режим сплит и очищает буфер."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        self._clear_split_dir(user_id)
        self._clear_split_media_groups(user_id)
        self._split_users.discard(user_id)
        self._split_prompt.pop(user_id, None)
        await message.answer(
            Msg.SPLIT_CANCELLED,
            reply_markup=ReplyKeyboardRemove(),
        )
        self._log_status(user_id, "split_cancelled")

    async def _handle_document(self, message: Message, document, filename: str | None) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not get_iiko_credentials(user_id):
            await message.answer(Msg.NO_IIKO_CREDENTIALS)
            return
        if not self._check_rate_limit(user_id):
            await message.answer(
                with_event_code(Msg.RATE_LIMIT, BOT_RATE_LIMIT)
            )
            self._log_status(user_id, "rate_limited", event_meta(BOT_RATE_LIMIT))
            return
        if user_id in self._split_users:
            if message.media_group_id:
                file = await self.bot.get_file(document.file_id)
                data = await self.bot.download_file(file.file_path)
                content = data.read()
                await self._add_split_media_group_file(
                    message,
                    user_id,
                    filename or "invoice.bin",
                    content,
                )
            else:
                is_duplicate = await self._store_split_file(document, filename or "invoice.bin", user_id)
                if is_duplicate:
                    await self._notify_soft_duplicate(message, user_id)
                await self._update_split_prompt(message, user_id)
            self._log_status(user_id, "split_file_added", {"filename": filename})
            return
        if message.media_group_id:
            file = await self.bot.get_file(document.file_id)
            data = await self.bot.download_file(file.file_path)
            content = data.read()
            await self._add_media_group_file(
                message,
                user_id,
                filename or "invoice.bin",
                content,
            )
            return
        is_duplicate = await self._store_pending_file(document, filename or "invoice.bin", user_id)
        if is_duplicate:
            await self._notify_soft_duplicate(message, user_id)
        self._log_status(user_id, "pending_file_added", {"filename": filename})
        if filename and filename.lower().endswith(".pdf"):
            self._ensure_pending_user(user_id, message.chat.id)
            await self._handle_pdf_mode_choice(message, user_id)
            return
        await self._handle_pending_choice(message, user_id)

    async def _handle_photo(self, message: Message, photo_list) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not get_iiko_credentials(user_id):
            await message.answer(Msg.NO_IIKO_CREDENTIALS)
            return
        max_mb = settings.max_upload_mb
        if message.photo and message.photo[-1].file_size:
            if message.photo[-1].file_size > max_mb * 1024 * 1024:
                await message.answer(
                    Msg.FILE_TOO_LARGE.format(max_mb=max_mb)
                )
                self._log_status(user_id, "file_too_large")
                return
        if not self._check_rate_limit(user_id):
            await message.answer(
                with_event_code(Msg.RATE_LIMIT, BOT_RATE_LIMIT)
            )
            self._log_status(user_id, "rate_limited", event_meta(BOT_RATE_LIMIT))
            return
        if user_id in self._split_users:
            largest = photo_list[-1]
            file = await self.bot.get_file(largest.file_id)
            data = await self.bot.download_file(file.file_path)
            content = data.read()
            if message.media_group_id:
                await self._add_split_media_group_file(
                    message,
                    user_id,
                    "invoice_photo.jpg",
                    content,
                )
            else:
                is_duplicate = await self._store_split_bytes("invoice_photo.jpg", content, user_id)
                if is_duplicate:
                    await self._notify_soft_duplicate(message, user_id)
                await self._update_split_prompt(message, user_id)

            self._log_status(user_id, "split_photo_added")
            return
        if message.media_group_id:
            largest = photo_list[-1]
            file = await self.bot.get_file(largest.file_id)
            data = await self.bot.download_file(file.file_path)
            content = data.read()
            await self._add_media_group_file(
                message,
                user_id,
                "invoice_photo.jpg",
                content,
            )
            return
        largest = photo_list[-1]
        file = await self.bot.get_file(largest.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        is_duplicate = await self._store_pending_bytes("invoice_photo.jpg", content, user_id)
        if is_duplicate:
            await self._notify_soft_duplicate(message, user_id)
        self._log_status(user_id, "pending_photo_added")
        await self._handle_pending_choice(message, user_id)

    async def on_document(self, message: Message) -> None:
        """Обрабатывает документ и пересылает его в backend."""
        document = message.document
        if document is None:
            return

        logger.info("Received document: %s", document.file_name or document.file_id)
        await self._handle_document(message, document, document.file_name)

    async def on_reply_to_file(self, message: Message) -> None:
        """Обрабатывает reply на сообщение с файлом/фото, без повторной загрузки."""
        if not message.from_user:
            return
        if message.document or message.photo:
            return
        reply = message.reply_to_message
        if reply is None:
            return
        if reply.document is not None:
            logger.info("Reply to document: %s", reply.document.file_name or reply.document.file_id)
            await self._handle_document(message, reply.document, reply.document.file_name)
            return
        if reply.photo:
            logger.info("Reply to photo from user_id=%s", message.from_user.id)
            await self._handle_photo(message, reply.photo)
            return

    async def on_photo(self, message: Message) -> None:
        """Обрабатывает фотографию и пересылает ее в backend."""
        if not message.photo:
            return

        logger.info("Received photo from user_id=%s", message.from_user.id if message.from_user else "unknown")
        await self._handle_photo(message, message.photo)

    async def on_unsupported_message(self, message: Message) -> None:
        """Отвечает пользователю при неподдерживаемом типе сообщения.

        Если это ответ на сообщение с файлом/фото, обрабатывает вложение.
        """
        if message.document or message.photo:
            return

        reply = message.reply_to_message
        if reply is not None:
            if reply.document is not None:
                logger.info("Reply to document: %s", reply.document.file_name or reply.document.file_id)
                await self._handle_document(message, reply.document, reply.document.file_name)
                return
            if reply.photo:
                logger.info("Reply to photo from user_id=%s", message.from_user.id)
                await self._handle_photo(message, reply.photo)
                return

        await message.answer(
            Msg.ACCEPTS_ONLY_SUPPORTED
        )

    async def _store_split_file(self, document, filename: str, user_id: str) -> bool:
        file = await self.bot.get_file(document.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        return await self._store_split_bytes(filename, content, user_id)

    async def _store_split_bytes(self, filename: str, content: bytes, user_id: str) -> bool:
        is_duplicate = self._is_duplicate(user_id, content)
        self._storage.store_split_bytes(user_id=user_id, filename=filename, content=content)
        return is_duplicate

    async def _store_pending_file(self, document, filename: str, user_id: str) -> bool:
        file = await self.bot.get_file(document.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        return await self._store_pending_bytes(filename, content, user_id)

    async def _store_pending_bytes(self, filename: str, content: bytes, user_id: str) -> bool:
        is_duplicate = self._is_duplicate(user_id, content)
        self._storage.store_pending_bytes(user_id=user_id, filename=filename, content=content)
        return is_duplicate

    def _collect_pending_files(self, user_id: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_pending_files(user_id)

    def _clear_pending_dir(self, user_id: str) -> None:
        self._storage.clear_pending_dir(user_id)

    def _deduplicate_pending_dir(self, user_id: str) -> dict[str, int]:
        return self._storage.deduplicate_pending_files(user_id)

    def _pending_duplicates_count(self, user_id: str) -> int:
        return self._storage.count_pending_duplicates(user_id)

    async def _accept_pending_as_split(
        self,
        message: Message,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(user_id)
        if not files:
            await message.answer(Msg.NO_PENDING)
            self._pending_users.discard(user_id)
            return
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        self._clear_split_dir(user_id)
        for name, content in files:
            await self._store_split_bytes(name, content, user_id)
        self._clear_pending_dir(user_id)
        self._pending_users.discard(user_id)
        self._pending_prompt.pop(user_id, None)
        self._split_users.add(user_id)
        if status_message:
            self._split_prompt[user_id] = status_message.message_id
        await self._update_split_prompt(message, user_id)

    async def _process_pending_as_batch(self, message: Message, user_id: str) -> None:
        await self._process_pending_as_batch_chat(message.chat.id, user_id)

    async def _process_pending_as_merged_batch_chat(
        self,
        chat_id: int,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        """Отправляет все pending-файлы одним батчем в backend."""
        files = self._collect_pending_files(user_id)
        if not files:
            await self.bot.send_message(chat_id, Msg.NO_PENDING)
            self._pending_users.discard(user_id)
            return

        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        self._clear_pending_dir(user_id)
        self._pending_users.discard(user_id)
        self._pending_prompt.pop(user_id, None)

        status_msg = status_message
        if status_msg:
            try:
                await status_msg.edit_text(
                    Msg.BATCH_COLLECTED.format(count=len(files)),
                    reply_markup=None,
                )
            except Exception:  # noqa: BLE001
                status_msg = None
        if status_msg is None:
            status_msg = await self.bot.send_message(
                chat_id,
                Msg.BATCH_COLLECTED.format(count=len(files)),
            )

        try:
            self._log_status(user_id, "backend_batch_sending", {"count": len(files), "source": "pending"})
            result = await send_batch_to_backend(
                self._backend_url,
                files,
                user_id,
                chat_id,
                status_message_id=status_msg.message_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Backend batch request failed")
            await status_msg.edit_text(Msg.BACKEND_FILES_ERROR)
            await self.bot.send_message(
                chat_id,
                with_event_code(Msg.BACKEND_SEND_FILES_FAILED, BOT_BACKEND_UNAVAILABLE),
            )
            self._log_status(
                user_id,
                "backend_batch_error",
                {"source": "pending", **event_meta(BOT_BACKEND_UNAVAILABLE)},
            )
            return

        await status_msg.edit_text(self._format_response(result), reply_markup=None)
        self._log_status(
            user_id,
            "backend_batch_done",
            {"request_id": result.get("request_id"), "source": "pending"},
        )

    async def _process_pending_as_batch_chat(
        self,
        chat_id: int,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(user_id)
        if not files:
            await self.bot.send_message(chat_id, Msg.NO_PENDING)
            self._pending_users.discard(user_id)
            return
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        self._clear_pending_dir(user_id)
        self._pending_users.discard(user_id)
        self._pending_prompt.pop(user_id, None)

        if len(files) == 1:
            name, content = files[0]
            status_msg = status_message
            if status_msg:
                try:
                    await status_msg.edit_text(Msg.FILE_RECEIVED_SENDING)
                except Exception:  # noqa: BLE001
                    try:
                        await status_msg.delete()
                    except Exception:  # noqa: BLE001
                        pass
                    status_msg = None
            if status_msg is None:
                status_msg = await self.bot.send_message(chat_id, Msg.FILE_RECEIVED_SENDING)
            try:
                await status_msg.edit_text(Msg.FILE_ON_SERVER_PROCESSING)
                self._log_status(user_id, "backend_sending", {"filename": name})
                result = await send_file_to_backend(
                    self._backend_url,
                    name,
                    content,
                    user_id,
                    chat_id,
                    status_message_id=status_msg.message_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Backend request failed")
                await status_msg.edit_text(Msg.BACKEND_FILE_ERROR)
                await self.bot.send_message(
                    chat_id,
                    with_event_code(Msg.BACKEND_SEND_FILE_FAILED, BOT_BACKEND_UNAVAILABLE),
                )
                self._log_status(
                    user_id,
                    "backend_error",
                    {"filename": name, **event_meta(BOT_BACKEND_UNAVAILABLE)},
                )
                return
            await status_msg.edit_text(self._format_response(result))
            self._log_status(user_id, "backend_done", {"request_id": result.get("request_id")})
            return

        status_msg = await self.bot.send_message(chat_id, Msg.PROCESSING_SEPARATELY.format(count=len(files)))
        for index, (name, content) in enumerate(files, start=1):
            try:
                await status_msg.edit_text(Msg.FILE_PROGRESS.format(index=index, total=len(files)))
                self._log_status(user_id, "backend_sending", {"filename": name, "index": index})
                result = await send_file_to_backend(self._backend_url, name, content, user_id, chat_id)
                await status_msg.edit_text(
                    Msg.FILE_DONE.format(index=index, total=len(files), result=self._format_response(result))
                )
                self._log_status(user_id, "backend_done", {"request_id": result.get("request_id")})
            except Exception:  # noqa: BLE001
                logger.exception("Backend request failed")
                await self.bot.send_message(
                    chat_id,
                    with_event_code(Msg.BACKEND_SEND_FILE_FAILED, BOT_BACKEND_UNAVAILABLE),
                )
                self._log_status(
                    user_id,
                    "backend_error",
                    {"filename": name, "index": index, **event_meta(BOT_BACKEND_UNAVAILABLE)},
                )

    async def _handle_pending_choice(self, message: Message, user_id: str) -> None:
        """Явный UI: после каждого файла показываем кнопки действия."""
        files = self._collect_pending_files(user_id)

        if not settings.enable_split_mode:
            await self._process_pending_as_batch_chat(message.chat.id, user_id)
            return

        if not files:
            await message.answer(Msg.NO_PENDING)
            return

        # Регистрируем пользователя в pending (без таймера)
        if user_id not in self._pending_users:
            self._pending_users.add(user_id)
            self._pending_chats[user_id] = message.chat.id

        if len(files) == 1:
            # Один файл — кнопка "Обработать" + возможность добавить ещё
            await self._send_single_file_keyboard(message, user_id)
            return

        # 2+ файлов — "Объединить" / "Ещё файл"
        await self._send_mode_keyboard(message)

    async def _add_media_group_file(self, message: Message, user_id: str | None, filename: str, content: bytes) -> None:
        group_id = str(message.media_group_id)
        entry = self._media_groups.get(group_id)
        if entry is None:
            entry = {
                "files": [],
                "user_id": user_id,
                "chat_id": message.chat.id,
                "message": message,
            }
            self._media_groups[group_id] = entry
        else:
            entry["message"] = message
        entry["files"].append((filename, content))
        if group_id not in self._media_group_tasks:
            self._media_group_tasks[group_id] = asyncio.create_task(self._finalize_media_group(group_id))

    async def _finalize_media_group(self, group_id: str) -> None:
        await asyncio.sleep(2)
        entry = self._media_groups.pop(group_id, None)
        self._media_group_tasks.pop(group_id, None)
        if not entry:
            return
        files = entry.get("files", [])
        user_id = entry.get("user_id")
        chat_id = entry.get("chat_id")
        if not files or chat_id is None:
            return

        # Если включен split-режим, то и для альбомов даём выбор объединения.
        if settings.enable_split_mode and user_id:
            duplicate_count = 0
            for name, content in files:
                if await self._store_pending_bytes(name, content, user_id):
                    duplicate_count += 1
            if duplicate_count:
                await self._notify_soft_duplicate_chat(chat_id, user_id, duplicate_count)
            self._pending_users.add(user_id)
            self._pending_chats[user_id] = chat_id
            await self._send_mode_keyboard_to_chat(chat_id, user_id)
            return

        status_msg = await self.bot.send_message(
            chat_id,
            Msg.MEDIA_GROUP_BATCH.format(count=len(files)),
        )
        try:
            self._log_status(user_id or "unknown", "media_group_batch_sending", {"count": len(files)})
            result = await send_batch_to_backend(
                self._backend_url,
                files,
                user_id,
                chat_id,
                status_message_id=status_msg.message_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Backend media group request failed")
            await status_msg.edit_text(Msg.BACKEND_FILES_ERROR)
            await self.bot.send_message(
                chat_id,
                with_event_code(Msg.BACKEND_SEND_FILES_FAILED, BOT_BACKEND_UNAVAILABLE),
            )
            self._log_status(
                user_id or "unknown",
                "media_group_batch_error",
                event_meta(BOT_BACKEND_UNAVAILABLE),
            )
            return
        await status_msg.edit_text(self._format_response(result))
        self._log_status(user_id or "unknown", "media_group_batch_done", {"request_id": result.get("request_id")})

    async def _add_split_media_group_file(self, message: Message, user_id: str, filename: str, content: bytes) -> None:
        group_id = str(message.media_group_id)
        entry = self._split_media_groups.get(group_id)
        if entry is None:
            entry = {
                "files": [],
                "user_id": user_id,
                "message": message,
            }
            self._split_media_groups[group_id] = entry
        else:
            entry["message"] = message
        entry["files"].append((filename, content))
        if group_id not in self._split_media_group_tasks:
            self._split_media_group_tasks[group_id] = asyncio.create_task(self._finalize_split_media_group(group_id))

    async def _finalize_split_media_group(
        self,
        group_id: str,
        *,
        debounce_seconds: float = 2.0,
        update_prompt: bool = True,
    ) -> None:
        if debounce_seconds > 0:
            await asyncio.sleep(debounce_seconds)

        entry = self._split_media_groups.pop(group_id, None)
        self._split_media_group_tasks.pop(group_id, None)
        if not entry:
            return

        files = entry.get("files", [])
        user_id = entry.get("user_id")
        message = entry.get("message")
        if not files or not user_id or message is None:
            return

        duplicate_count = 0
        for name, content in files:
            if await self._store_split_bytes(name, content, user_id):
                duplicate_count += 1

        if duplicate_count:
            await self._notify_soft_duplicate(message, user_id, duplicate_count)

        if update_prompt:
            await self._update_split_prompt(message, user_id)
        self._log_status(user_id, "split_media_group_added", {"count": len(files), "duplicates": duplicate_count})

    async def _send_single_file_keyboard(self, message: Message, user_id: str) -> None:
        """Один файл в pending: показываем только кнопку запуска обработки."""
        text = Msg.PENDING_SINGLE
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=Msg.BTN_PROCESS_NOW, callback_data="mode:process", style="primary")],
            ]
        )
        sent = await message.answer(text, reply_markup=keyboard)
        self._pending_prompt[user_id] = sent.message_id

    async def _send_mode_keyboard(self, message: Message) -> None:
        """2+ файлов — показываем 'Объединить' / 'Ещё файл'."""
        user_id = str(message.from_user.id) if message.from_user else ""
        await self._send_mode_keyboard_to_chat(message.chat.id, user_id)

    async def _send_mode_keyboard_to_chat(self, chat_id: int, user_id: str) -> None:
        files = self._collect_pending_files(user_id)
        duplicate_count = self._pending_duplicates_count(user_id)
        text = Msg.PENDING_MULTI.format(count=len(files))
        if duplicate_count > 0:
            text += Msg.PENDING_DUPS.format(count=duplicate_count)

        rows = [[InlineKeyboardButton(text=Msg.BTN_MERGE_SEND, callback_data="mode:merge", style="success")]]
        if duplicate_count > 0:
            rows.append([InlineKeyboardButton(text=Msg.BTN_DEDUP, callback_data="mode:dedup", style="danger")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        old_id = self._pending_prompt.get(user_id)
        sent = await self.bot.send_message(chat_id, text, reply_markup=keyboard)
        self._pending_prompt[user_id] = sent.message_id
        if old_id:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=old_id)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to delete pending prompt for user_id=%s", user_id)

    async def on_mode_choice(self, query: CallbackQuery) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        data = (query.data or "").strip().lower()
        await query.answer()

        if data.startswith("split:"):
            await self._handle_split_choice(query, data)
            return

        if data.startswith("pdf:"):
            await self._handle_pdf_choice(query, data)
            return
        if data.startswith("inv:"):
            await self._handle_invoice_actions(query, data)
            return
        if data.startswith("edit:"):
            await self._handle_edit_actions(query, data)
            return

        # "Добавить ещё" — просто убираем клавиатуру, ждём следующий файл
        if data == "mode:wait":
            await query.message.edit_text(Msg.PENDING_WAIT)
            return

        if not self._ensure_pending_user(user_id, query.message.chat.id):
            await query.message.answer(
                with_event_code(
                    Msg.NO_PENDING_REUPLOAD,
                    BOT_NO_PENDING,
                )
            )
            self._log_status(user_id, "no_pending_on_action", event_meta(BOT_NO_PENDING))
            return

        # Отменяем старый таймер, если вдруг остался
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()

        if data == "mode:process":
            status_message = query.message
            try:
                await status_message.edit_text(Msg.SENDING_PROCESS)
            except Exception:  # noqa: BLE001
                status_message = None
            await self._process_pending_as_batch_chat(
                query.message.chat.id,
                user_id,
                status_message=status_message,
            )
            self._log_status(user_id, "mode_selected", {"mode": "process"})
            return
        if data == "mode:merge":
            status_message = query.message
            try:
                await status_message.edit_text(Msg.MERGING_SENDING, reply_markup=None)
            except Exception:  # noqa: BLE001
                status_message = None
            await self._process_pending_as_merged_batch_chat(
                query.message.chat.id,
                user_id,
                status_message=status_message,
            )
            self._log_status(user_id, "mode_selected", {"mode": "merge"})
            return
        if data == "mode:dedup":
            stats = self._deduplicate_pending_dir(user_id)
            await query.message.edit_text(Msg.DEDUP_DONE.format(removed=stats["removed"], kept=stats["kept"]))
            await self._handle_pending_choice(query.message, user_id)
            self._log_status(user_id, "pending_deduplicated", stats)
            return
        await query.message.answer(Msg.MODE_UNKNOWN)

    async def _handle_invoice_actions(self, query: CallbackQuery, data: str) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.answer(Msg.BAD_COMMAND)
            return
        action, request_id = parts[1], parts[2]
        await query.answer()

        if action == "cancel":
            await query.message.edit_text(Msg.ACTION_CANCELLED, reply_markup=None)
            self._edit_state.pop(user_id, None)
            return

        if action == "edit":
            payload = self._load_request_payload(request_id)
            if not payload:
                await query.message.answer(Msg.EDIT_NOT_FOUND_REQUEST)
                return
            state = EditState(request_id=request_id, payload=payload)
            self._edit_state[user_id] = state
            await self._show_edit_menu(query.message, state)
            return

        if action == "send":
            await self._send_to_iiko(query.message, request_id)
            return

    async def _handle_edit_actions(self, query: CallbackQuery, data: str) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        state = self._edit_state.get(user_id)
        if not state:
            await query.message.answer(Msg.EDIT_NO_ACTIVE)
            return
        await query.answer()

        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[1]

        if action == "menu":
            await self._show_edit_menu(query.message, state)
            return
        if action == "info":
            await self._show_info_fields(query.message, state)
            return
        if action == "items":
            await self._show_items_list(query.message, state)
            return
        if action == "done":
            await self._show_final_response(query.message, state)
            return
        if action == "cancel":
            self._edit_state.pop(user_id, None)
            await query.message.edit_text(Msg.EDIT_CANCELLED, reply_markup=None)
            return
        if action == "field" and len(parts) == 3:
            field = parts[2]
            state.mode = "info"
            state.awaiting = field
            await query.message.edit_text(
                Msg.EDIT_ENTER_FIELD.format(field=INFO_FIELDS.get(field, field)),
                reply_markup=self._cancel_keyboard(),
            )
            return
        if action == "item" and len(parts) == 3:
            index = int(parts[2])
            state.mode = "item"
            state.item_index = index
            await self._show_item_fields(query.message, state)
            return
        if action == "itemfield" and len(parts) == 3:
            field = parts[2]
            state.mode = "itemfield"
            state.awaiting = field
            await query.message.edit_text(
                Msg.EDIT_ENTER_ITEM_FIELD.format(field=ITEM_FIELDS.get(field, field)),
                reply_markup=self._cancel_keyboard(),
            )
            return

    async def _handle_edit_text(self, message: Message, user_id: str) -> bool:
        state = self._edit_state.get(user_id)
        if not state or not state.awaiting:
            return False
        text = (message.text or "").strip()
        if not text:
            return False

        if state.mode == "info":
            state.overrides[state.awaiting] = text
            state.awaiting = None
            await self._show_info_fields(message, state)
            return True
        if state.mode == "itemfield" and state.item_index is not None:
            items = state.items
            if 0 <= state.item_index < len(items):
                items[state.item_index][state.awaiting] = text
            state.awaiting = None
            await self._show_item_fields(message, state)
            return True
        return False

    async def _show_edit_menu(self, message: Message, state: "EditState") -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=Msg.BTN_EDIT_INFO, callback_data="edit:info"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_EDIT_ITEMS, callback_data="edit:items"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_DONE, callback_data="edit:done", style="success"),
                    InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data="edit:cancel", style="danger"),
                ],
            ]
        )
        await self._reply(message, Msg.EDIT_WHAT, reply_markup=keyboard)

    async def _show_info_fields(self, message: Message, state: "EditState") -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=Msg.INFO_FIELDS["supplier"], callback_data="edit:field:supplier"),
                    InlineKeyboardButton(text=Msg.INFO_FIELDS["consignee"], callback_data="edit:field:consignee"),
                ],
                [
                    InlineKeyboardButton(text=Msg.INFO_FIELDS["delivery_address"], callback_data="edit:field:delivery_address"),
                ],
                [
                    InlineKeyboardButton(text=Msg.INFO_FIELDS["invoice_date"], callback_data="edit:field:invoice_date"),
                    InlineKeyboardButton(text=Msg.INFO_FIELDS["invoice_number"], callback_data="edit:field:invoice_number"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_BACK, callback_data="edit:menu"),
                    InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data="edit:cancel", style="danger"),
                ],
            ]
        )
        await self._reply(message, Msg.EDIT_SELECT_FIELD, reply_markup=keyboard)

    async def _show_items_list(self, message: Message, state: "EditState") -> None:
        buttons: list[list[InlineKeyboardButton]] = []
        for idx, item in enumerate(state.items[:10], start=1):
            title = item.get("name") or Msg.ITEM_FALLBACK.format(idx=idx)
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=Msg.BTN_ITEM_ROW.format(index=idx, title=title[:32]),
                        callback_data=f"edit:item:{idx-1}",
                    )
                ]
            )
        buttons.append(
            [
                InlineKeyboardButton(text=Msg.BTN_BACK, callback_data="edit:menu"),
                InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data="edit:cancel", style="danger"),
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await self._reply(message, Msg.EDIT_SELECT_ITEM, reply_markup=keyboard)

    async def _show_item_fields(self, message: Message, state: "EditState") -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=Msg.BTN_ITEM_NAME, callback_data="edit:itemfield:name"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_ITEM_QTY, callback_data="edit:itemfield:unit_amount"),
                    InlineKeyboardButton(text=Msg.BTN_ITEM_PRICE, callback_data="edit:itemfield:unit_price"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_ITEM_TOTAL, callback_data="edit:itemfield:cost_with_tax"),
                    InlineKeyboardButton(text=Msg.BTN_ITEM_VAT, callback_data="edit:itemfield:tax_amount"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_BACK, callback_data="edit:items"),
                    InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data="edit:cancel", style="danger"),
                ],
            ]
        )
        await self._reply(message, Msg.EDIT_SELECT_ITEM_FIELD, reply_markup=keyboard)

    async def _show_final_response(self, message: Message, state: "EditState") -> None:
        text = format_invoice_markdown(
            state.payload,
            overrides=state.overrides,
            items_override=state.items,
        )
        await self._reply(message, text, reply_markup=self._invoice_actions(state.request_id))

    async def _reply(
        self,
        message: Message,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except Exception:  # noqa: BLE001
            pass
        await message.answer(text, reply_markup=reply_markup)

    def _invoice_actions(self, request_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=Msg.BTN_INV_EDIT, callback_data=f"inv:edit:{request_id}", style="primary"),
                    InlineKeyboardButton(text=Msg.BTN_INV_SEND, callback_data=f"inv:send:{request_id}", style="success"),
                ],
                [
                    InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data=f"inv:cancel:{request_id}", style="danger"),
                ],
            ]
        )

    def _cancel_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=Msg.BTN_CANCEL, callback_data="edit:cancel", style="danger")]]
        )

    async def _send_to_iiko(self, message: Message, request_id: str) -> None:
        code = short_request_code(request_id) or request_id
        code_line = Msg.CODE_LINE.format(code=code) if code else ""
        payload_path = Path(__file__).resolve().parents[2] / "data" / "jobs" / request_id / "payload.json"
        if not payload_path.exists():
            await message.edit_text(
                Msg.IIKO_SOURCE_MISSING.format(code_line=code_line),
                reply_markup=None,
            )
            return
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        files = payload.get("files")
        filename = payload.get("filename")
        file_path = payload.get("file_path")
        user_id = payload.get("user_id")
        chat_id = payload.get("chat_id")
        status_message_id = payload.get("status_message_id")

        try:
            if files:
                batch: list[tuple[str, bytes]] = []
                for name, path in files:
                    batch.append((name, Path(path).read_bytes()))
                result = await send_batch_to_backend(
                    self._backend_url,
                    batch,
                    user_id,
                    chat_id,
                    status_message_id=status_message_id,
                    push_to_iiko_override=True,
                )
            else:
                if not filename or not file_path:
                    await message.edit_text(
                        Msg.IIKO_FILE_NOT_FOUND.format(code_line=code_line),
                        reply_markup=None,
                    )
                    return
                result = await send_file_to_backend(
                    self._backend_url,
                    filename,
                    Path(file_path).read_bytes(),
                    user_id,
                    chat_id,
                    status_message_id=status_message_id,
                    push_to_iiko_override=True,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send to iiko")
            await message.edit_text(
                Msg.IIKO_FAILED.format(code_line=code_line),
                reply_markup=None,
            )
            return

        if result.get("status") == "ok" and result.get("iiko_uploaded"):
            await message.edit_text(
                Msg.IIKO_OK.format(code_line=code_line),
                reply_markup=None,
            )
            return
        await message.edit_text(
            Msg.IIKO_FAILED.format(code_line=code_line),
            reply_markup=None,
        )

    def _load_request_payload(self, request_id: str) -> dict[str, Any] | None:
        path = Path(__file__).resolve().parents[2] / "logs" / "requests" / f"{request_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None


    async def _handle_pdf_mode_choice(self, message: Message, user_id: str) -> None:
        """Показывает выбор режима PDF перед обработкой."""
        current = get_pdf_mode(user_id)
        text = Msg.PDF_MODE.format(current=current)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=Msg.BTN_FAST, callback_data="pdf:fast", style="primary")],
                [InlineKeyboardButton(text=Msg.BTN_ACCURATE, callback_data="pdf:accurate", style="default")],
            ]
        )
        sent = await message.answer(text, reply_markup=keyboard)
        self._pending_prompt[user_id] = sent.message_id

    async def _handle_pdf_choice(self, query: CallbackQuery, data: str) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        await query.answer()

        if not self._ensure_pending_user(user_id, query.message.chat.id):
            await query.message.answer(
                with_event_code(
                    Msg.NO_PENDING_FILE_REUPLOAD,
                    BOT_NO_PENDING,
                )
            )
            self._log_status(user_id, "no_pending_on_pdf_action", event_meta(BOT_NO_PENDING))
            return

        if data == "pdf:fast":
            set_pdf_mode(user_id, "fast")
            await query.message.edit_text(Msg.PDF_SET_FAST)
            self._log_status(user_id, "mode_selected", {"mode": "pdf_fast"})
            await self._process_pending_as_batch_chat(
                query.message.chat.id,
                user_id,
                status_message=query.message,
            )
            return
        if data == "pdf:accurate":
            set_pdf_mode(user_id, "accurate")
            await query.message.edit_text(Msg.PDF_SET_ACCURATE)
            self._log_status(user_id, "mode_selected", {"mode": "pdf_accurate"})
            await self._process_pending_as_batch_chat(
                query.message.chat.id,
                user_id,
                status_message=query.message,
            )
            return
        if data == "pdf:process":
            self._log_status(user_id, "mode_selected", {"mode": "pdf_process"})
            await self._process_pending_as_batch_chat(
                query.message.chat.id,
                user_id,
                status_message=query.message,
            )
            return

    async def _handle_split_choice(self, query: CallbackQuery, data: str) -> None:
        """Обрабатывает кнопки split-режима."""
        if not query.from_user:
            return
        user_id = str(query.from_user.id)

        if user_id not in self._split_users:
            await query.message.edit_text(Msg.SPLIT_NOT_ENABLED_SHORT)
            return

        if data == "split:wait":
            await query.message.edit_text(Msg.SPLIT_WAIT)
            return
        if data == "split:dedup":
            stats = self._deduplicate_split_dir(user_id)
            await query.message.edit_text(Msg.DEDUP_DONE.format(removed=stats["removed"], kept=stats["kept"]))
            await self._update_split_prompt(query.message, user_id)
            self._log_status(user_id, "split_deduplicated", stats)
            return

        if data == "split:cancel":
            self._clear_split_dir(user_id)
            self._clear_split_media_groups(user_id)
            self._split_users.discard(user_id)
            self._split_prompt.pop(user_id, None)
            await query.message.edit_text(
                Msg.SPLIT_CANCEL_INFO,
                reply_markup=None,
            )
            self._log_status(user_id, "split_cancelled")
            return

        if data == "split:done":
            await self._finalize_split(
                query.message.chat.id,
                user_id,
                status_message=query.message,
            )
            return

        await query.message.answer(Msg.MODE_UNKNOWN)

    async def _update_split_prompt(self, message: Message, user_id: str) -> None:
        """Обновляет единое сообщение split-режима с кнопками."""
        count = len(self._collect_split_files(user_id))
        text, keyboard = self._build_split_prompt(user_id, count)
        old_id = self._split_prompt.get(user_id)
        sent = await message.answer(text, reply_markup=keyboard)
        self._split_prompt[user_id] = sent.message_id
        if old_id:
            try:
                await self.bot.delete_message(chat_id=message.chat.id, message_id=old_id)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to delete split prompt for user_id=%s", user_id)

    async def _finalize_split(
        self,
        chat_id: int,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        """Отправляет split-части на backend и редактирует статусное сообщение."""
        await self._flush_split_media_groups(user_id)
        files = self._collect_split_files(user_id)
        if not files:
            if status_message:
                await status_message.edit_text(
                    Msg.SPLIT_EMPTY,
                    reply_markup=None,
                )
                await self._update_split_prompt(status_message, user_id)
            else:
                text, keyboard = self._build_split_prompt(user_id, 0)
                sent = await self.bot.send_message(chat_id, text, reply_markup=keyboard)
                self._split_prompt[user_id] = sent.message_id
            return

        self._log_status(user_id, "split_finish_requested")
        status_msg = status_message
        if status_msg:
            try:
                await status_msg.edit_text(Msg.SPLIT_SENDING, reply_markup=None)
            except Exception:  # noqa: BLE001
                try:
                    await status_msg.delete()
                except Exception:  # noqa: BLE001
                    pass
                status_msg = None
        if status_msg is None:
            # Удаляем старое split-сообщение, чтобы не оставлять “висячие” кнопки.
            message_id = self._split_prompt.get(user_id)
            if message_id:
                try:
                    await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:  # noqa: BLE001
                    pass
            status_msg = await self.bot.send_message(
                chat_id,
                Msg.BATCH_COLLECTED.format(count=len(files)),
            )

        try:
            self._log_status(user_id, "backend_batch_sending", {"count": len(files)})
            result = await send_batch_to_backend(
                self._backend_url,
                files,
                user_id,
                chat_id,
                status_message_id=status_msg.message_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Backend batch request failed")
            await status_msg.edit_text(Msg.BACKEND_FILES_ERROR)
            await self.bot.send_message(
                chat_id,
                with_event_code(Msg.BACKEND_SEND_FILES_FAILED, BOT_BACKEND_UNAVAILABLE),
            )
            self._log_status(user_id, "backend_batch_error", event_meta(BOT_BACKEND_UNAVAILABLE))
            return
        finally:
            self._clear_split_dir(user_id)
            self._clear_split_media_groups(user_id)
            self._split_users.discard(user_id)
            self._split_prompt.pop(user_id, None)

        await status_msg.edit_text(self._format_response(result), reply_markup=None)
        self._log_status(user_id, "backend_batch_done", {"request_id": result.get("request_id")})

    def _build_split_prompt(self, user_id: str, count: int) -> tuple[str, InlineKeyboardMarkup]:
        duplicate_count = self._split_duplicates_count(user_id)
        text = Msg.SPLIT_PROMPT.format(count=count)
        if duplicate_count > 0:
            text += Msg.SPLIT_DUPS.format(count=duplicate_count)

        first_row = [InlineKeyboardButton(text=Msg.BTN_SPLIT_CANCEL, callback_data="split:cancel", style="danger")]
        if duplicate_count > 0:
            first_row.append(InlineKeyboardButton(text=Msg.BTN_DEDUP, callback_data="split:dedup", style="danger"))

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                first_row,
                [
                    InlineKeyboardButton(text=Msg.BTN_SPLIT_DONE, callback_data="split:done", style="success"),
                ],
            ]
        )
        return text, keyboard

    @staticmethod
    def _soft_duplicate_text(duplicate_count: int = 1) -> str:
        if duplicate_count <= 1:
            return Msg.SOFT_DUP_ONE
        return Msg.SOFT_DUP_MANY.format(count=duplicate_count)

    async def _notify_soft_duplicate(self, message: Message, user_id: str, duplicate_count: int = 1) -> None:
        if duplicate_count <= 0:
            return
        await message.answer(self._soft_duplicate_text(duplicate_count))
        self._log_status(user_id, "soft_duplicate_detected", {"count": duplicate_count})

    async def _notify_soft_duplicate_chat(self, chat_id: int, user_id: str, duplicate_count: int = 1) -> None:
        if duplicate_count <= 0:
            return
        await self.bot.send_message(chat_id, self._soft_duplicate_text(duplicate_count))
        self._log_status(user_id, "soft_duplicate_detected", {"count": duplicate_count})

    def _clear_split_media_groups(self, user_id: str) -> None:
        group_ids = [group_id for group_id, entry in self._split_media_groups.items() if entry.get("user_id") == user_id]
        for group_id in group_ids:
            self._split_media_groups.pop(group_id, None)
            task = self._split_media_group_tasks.pop(group_id, None)
            if task:
                task.cancel()

    async def _flush_split_media_groups(self, user_id: str) -> None:
        group_ids = [group_id for group_id, entry in self._split_media_groups.items() if entry.get("user_id") == user_id]
        for group_id in group_ids:
            task = self._split_media_group_tasks.pop(group_id, None)
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await self._finalize_split_media_group(group_id, debounce_seconds=0, update_prompt=False)

    def _reset_user_buffers(self, user_id: str) -> None:
        """Очищает pending/split состояния пользователя, чтобы не тянуть старые файлы."""
        self._clear_pending_dir(user_id)
        self._clear_split_dir(user_id)
        self._clear_split_media_groups(user_id)
        self._pending_users.discard(user_id)
        self._split_users.discard(user_id)
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        self._pending_prompt.pop(user_id, None)
        self._split_prompt.pop(user_id, None)

    def _ensure_pending_user(self, user_id: str, chat_id: int) -> bool:
        if user_id in self._pending_users:
            self._pending_chats[user_id] = chat_id
            return True
        if not self._collect_pending_files(user_id):
            return False
        self._pending_users.add(user_id)
        self._pending_chats[user_id] = chat_id
        return True

    def _collect_split_files(self, user_id: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_split_files(user_id)

    def _clear_split_dir(self, user_id: str) -> None:
        self._storage.clear_split_dir(user_id)

    def _deduplicate_split_dir(self, user_id: str) -> dict[str, int]:
        return self._storage.deduplicate_split_files(user_id)

    def _split_duplicates_count(self, user_id: str) -> int:
        return self._storage.count_split_duplicates(user_id)

    def _log_status(self, user_id: str, event: str, extra: dict | None = None) -> None:
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user_id": user_id,
            "event": event,
            "extra": extra or {},
        }
        try:
            # На всякий случай убеждаемся, что каталог для логов существует
            STATUS_LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = STATUS_LOG_DIR / f"{user_id}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False))
                handle.write("\n")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to append status log")

    def _cleanup_pending_dirs(self) -> None:
        cutoff = datetime.now() - timedelta(hours=12)
        for base in (self._pending_dir, self._split_dir):
            if not base.exists():
                continue
            for user_dir in base.iterdir():
                if not user_dir.is_dir():
                    continue
                for item in user_dir.iterdir():
                    try:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        if mtime < cutoff:
                            item.unlink()
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to cleanup pending file")

    def _check_rate_limit(self, user_id: str | None) -> bool:
        if not user_id:
            return True
        now = datetime.now()
        window = now - timedelta(minutes=1)
        history = self._rate_limits.get(user_id, [])
        history = [ts for ts in history if ts > window]
        history.append(now)
        self._rate_limits[user_id] = history
        return len(history) <= settings.max_files_per_minute

    def _is_duplicate(self, user_id: str | None, content: bytes) -> bool:
        if not user_id:
            return False
        digest = hashlib.sha256(content).hexdigest()
        now = datetime.now()
        bucket = self._recent_hashes.get(user_id, {})
        cutoff = now - timedelta(minutes=10)
        bucket = {k: v for k, v in bucket.items() if v > cutoff}
        if digest in bucket:
            self._recent_hashes[user_id] = bucket
            return True
        bucket[digest] = now
        self._recent_hashes[user_id] = bucket
        return False

    def _format_response(self, payload: dict) -> str:
        """Форматирует сообщение пользователю.

        Пояснение человеческим языком:
        - внутри системы request_id длинный и нужен для уникальности (логи/БД);
        - пользователю показываем короткий «Код заявки» из 5 цифр,
          чтобы его было легко продиктовать/вставить.

        Логику форматирования держим в одном месте (app.utils.user_messages),
        чтобы бот и воркер писали одинаково.
        """

        return format_user_response(payload)


@dataclass
class EditState:
    request_id: str
    payload: dict[str, Any]
    overrides: dict[str, str] = None
    items: list[dict[str, Any]] = None
    mode: str | None = None
    awaiting: str | None = None
    item_index: int | None = None

    def __post_init__(self) -> None:
        self.overrides = self.overrides or {}
        parsed = self.payload.get("parsed") or {}
        self.items = self.items or list(parsed.get("items") or self.payload.get("items") or [])


INFO_FIELDS = Msg.INFO_FIELDS

ITEM_FIELDS = Msg.ITEM_FIELDS
