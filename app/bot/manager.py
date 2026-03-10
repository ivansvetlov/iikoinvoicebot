"""Модуль управления Telegram-ботом и его обработчиками."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.bot.backend_client import send_batch_to_backend, send_file_to_backend
from app.bot.file_storage import PendingSplitStorage
from app.config import settings
from app.services.user_store import (
    get_iiko_credentials,
    get_pdf_mode,
    set_iiko_credentials,
    set_pdf_mode,
)
from app.utils.user_messages import format_user_response

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
        self._rate_limits: dict[str, list[datetime]] = {}
        self._recent_hashes: dict[str, dict[str, datetime]] = {}
        logger.info("Bot manager initialized")
        self._storage.cleanup_old()

    async def run(self) -> None:
        """Запускает polling-цикл бота."""
        logger.info("Starting bot polling")
        logger.info("✅ Bot ready, polling started")
        await self.dp.start_polling(self.bot)

    def _register_handlers(self) -> None:
        """Регистрирует обработчики сообщений."""
        self.dp.message.register(self.start, CommandStart())
        # /mode \/ /modefast \/ /modeaccurate
        self.dp.message.register(self.set_mode, Command("mode"))
        self.dp.message.register(self.set_mode_fast, Command("modefast"))
        self.dp.message.register(self.set_mode_accurate, Command("modeaccurate"))

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
            await message.answer("Вы уже авторизованы в iiko. Можете отправлять накладные.")
            return
        await message.answer("Для работы с iiko нужна авторизация. Введите логин iiko:")
        self._auth_state[user_id] = "await_login"
        self._log_status(user_id, "auth_requested", {"message_id": message.message_id})

    async def set_mode(self, message: Message) -> None:
        """Показывает и (опционально) меняет режим обработки PDF.

        Варианты использования для пользователя:
        - `/mode` — просто показать текущий режим и краткие подсказки.
        - `/mode fast` или `/mode accurate` — переключить режим.

        Отдельные команды `/modefast` и `/modeaccurate` обрабатываются
        хендлерами `set_mode_fast` / `set_mode_accurate`.
        """
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        text = (message.text or "").strip().lower()
        parts = text.split()

        # Только /mode — показать текущий режим и подсказки.
        if len(parts) == 1:
            current = get_pdf_mode(user_id)
            await message.answer(
                "Режим обработки PDF:\n"
                f"Сейчас: {current}\n"
                "fast — быстрее и дешевле, но может пропускать строки.\n"
                "accurate — точнее, но медленнее и дороже.\n"
                "Можно использовать: /mode fast или /mode accurate."
            )
            return

        # /mode fast | /mode accurate
        mode = parts[1].strip().lower()
        if mode not in {"fast", "accurate"}:
            await message.answer(
                "Неверный режим. Используйте `/mode fast` или `/mode accurate`."
            )
            return

        set_pdf_mode(user_id, mode)
        await message.answer(f"Готово. Режим PDF: {mode}.")

    async def set_mode_fast(self, message: Message) -> None:
        """Явная команда /modefast — переключает режим PDF в fast."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        set_pdf_mode(user_id, "fast")
        await message.answer("Готово. Режим PDF: fast.")

    async def set_mode_accurate(self, message: Message) -> None:
        """Явная команда /modeaccurate — переключает режим PDF в accurate."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        set_pdf_mode(user_id, "accurate")
        await message.answer("Готово. Режим PDF: accurate.")

    async def on_text(self, message: Message) -> None:
        """Обрабатывает текстовые сообщения для авторизации."""
        if not message.from_user:
            return

        user_id = str(message.from_user.id)
        if user_id in self._pending_users:
            text = (message.text or "").strip().lower()
            if text in {"merge", "объединить", "с"}:
                await self._accept_pending_as_split(message, user_id)
                self._log_status(user_id, "mode_selected", {"mode": "merge"})
                return

        state = self._auth_state.get(user_id)
        if not state:
            await message.answer(
                "Я принимаю фото, PDF или DOCX накладной. "
                "Если нужна авторизация — используйте /start."
            )
            return

        text = (message.text or "").strip()
        if not text:
            return

        if state == "await_login":
            self._pending_login[user_id] = text
            self._auth_state[user_id] = "await_password"
            await message.answer("Теперь введите пароль iiko:")
            self._log_status(user_id, "auth_login_received")
            return

        if state == "await_password":
            login = self._pending_login.get(user_id)
            if not login:
                self._auth_state[user_id] = "await_login"
                await message.answer("Логин не найден. Введите логин iiko:")
                return
            set_iiko_credentials(user_id, login, text)
            self._auth_state.pop(user_id, None)
            self._pending_login.pop(user_id, None)
            await message.answer("Данные сохранены. Теперь можно отправлять накладные.")
            self._log_status(user_id, "auth_completed")
            return
        await message.answer(
            "Я принимаю фото, PDF или DOCX накладной. "
            "Если нужна авторизация — используйте /start."
        )

    async def start_split(self, message: Message) -> None:
        """Включает режим сплит для объединения нескольких файлов в одну накладную."""
        if not message.from_user:
            return
        if not settings.enable_split_mode:
            await message.answer("Режим объединения сейчас отключен.")
            return
        user_id = str(message.from_user.id)
        if not get_iiko_credentials(user_id):
            await message.answer("Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию.")
            return
        self._split_users.add(user_id)
        self._clear_split_dir(user_id)
        # На старте split очищаем pending, чтобы не смешивать режимы.
        self._clear_pending_dir(user_id)
        self._pending_users.discard(user_id)
        self._pending_tasks.pop(user_id, None)
        self._pending_prompt.pop(user_id, None)

        await message.answer(
            "Режим объединения включен. Отправляйте части накладной.",
            reply_markup=ReplyKeyboardRemove(),
        )
        self._log_status(user_id, "split_started")

    async def finish_split(self, message: Message) -> None:
        """Завершает режим сплит и отправляет все части на обработку."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        if user_id not in self._split_users:
            await message.answer("Режим объединения не включен. Введите /split для начала.")
            return
        await message.answer("Завершаю режим объединения.", reply_markup=ReplyKeyboardRemove())
        await self._finalize_split(message.chat.id, user_id, status_message=None)

    async def cancel_split(self, message: Message) -> None:
        """Отменяет режим сплит и очищает буфер."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        self._clear_split_dir(user_id)
        self._split_users.discard(user_id)
        self._split_prompt.pop(user_id, None)
        await message.answer(
            "Режим объединения отменен. Буфер очищен.",
            reply_markup=ReplyKeyboardRemove(),
        )
        self._log_status(user_id, "split_cancelled")

    async def _handle_document(self, message: Message, document, filename: str | None) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not get_iiko_credentials(user_id):
            await message.answer(
                "Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию."
            )
            return
        if not self._check_rate_limit(user_id):
            await message.answer(
                "Сейчас слишком много файлов. Я продолжу обработку через минуту. "
                "Если нужно срочно — отправьте позже.\n"
                "Код события: BOT_RATE_LIMIT"
            )
            self._log_status(user_id, "rate_limited")
            return
        if user_id in self._split_users:
            await self._store_split_file(document, filename or "invoice.bin", user_id)
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
        await self._store_pending_file(document, filename or "invoice.bin", user_id)
        self._log_status(user_id, "pending_file_added", {"filename": filename})
        await self._handle_pending_choice(message, user_id)

    async def _handle_photo(self, message: Message, photo_list) -> None:
        user_id = str(message.from_user.id) if message.from_user else None
        if not get_iiko_credentials(user_id):
            await message.answer(
                "Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию."
            )
            return
        max_mb = settings.max_upload_mb
        if message.photo and message.photo[-1].file_size:
            if message.photo[-1].file_size > max_mb * 1024 * 1024:
                await message.answer(
                    f"Фото слишком большое (лимит {max_mb} MB). "
                    "Сожмите фото и отправьте снова."
                )
                self._log_status(user_id, "file_too_large")
                return
        if not self._check_rate_limit(user_id):
            await message.answer(
                "Сейчас слишком много файлов. Я продолжу обработку через минуту. "
                "Если нужно срочно — отправьте позже.\n"
                "Код события: BOT_RATE_LIMIT"
            )
            self._log_status(user_id, "rate_limited")
            return
        if user_id in self._split_users:
            # В режиме split просто накапливаем части в буфере. Пользователю важно
            # понимать, что делать дальше, поэтому после каждого фото показываем
            # текущий прогресс и напоминаем про /done и /cancel.
            largest = photo_list[-1]
            file = await self.bot.get_file(largest.file_id)
            data = await self.bot.download_file(file.file_path)
            content = data.read()
            await self._store_split_bytes("invoice_photo.jpg", content, user_id)
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
        await self._store_pending_bytes("invoice_photo.jpg", content, user_id)
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
            "Я принимаю только фото, PDF или DOCX накладной. "
            "Отправьте файл, и я верну статус обработки."
        )

    async def _store_split_file(self, document, filename: str, user_id: str) -> None:
        file = await self.bot.get_file(document.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        await self._store_split_bytes(filename, content, user_id)

    async def _store_split_bytes(self, filename: str, content: bytes, user_id: str) -> None:
        self._storage.store_split_bytes(user_id=user_id, filename=filename, content=content)

    async def _store_pending_file(self, document, filename: str, user_id: str) -> None:
        file = await self.bot.get_file(document.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        await self._store_pending_bytes(filename, content, user_id)

    async def _store_pending_bytes(self, filename: str, content: bytes, user_id: str) -> None:
        self._storage.store_pending_bytes(user_id=user_id, filename=filename, content=content)

    def _collect_pending_files(self, user_id: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_pending_files(user_id)

    def _clear_pending_dir(self, user_id: str) -> None:
        self._storage.clear_pending_dir(user_id)

    async def _accept_pending_as_split(
        self,
        message: Message,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(user_id)
        if not files:
            await message.answer("Нет ожидающих файлов.")
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

    async def _process_pending_as_batch_chat(
        self,
        chat_id: int,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(user_id)
        if not files:
            await self.bot.send_message(chat_id, "Нет ожидающих файлов.")
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
                    await status_msg.edit_text("Файл получен. Отправляю на сервер…")
                except Exception:  # noqa: BLE001
                    try:
                        await status_msg.delete()
                    except Exception:  # noqa: BLE001
                        pass
                    status_msg = None
            if status_msg is None:
                status_msg = await self.bot.send_message(chat_id, "Файл получен. Отправляю на сервер…")
            try:
                await status_msg.edit_text("Файл на сервере. Идет обработка…")
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
                await status_msg.edit_text("Ошибка при обработке файла.")
                await self.bot.send_message(
                    chat_id,
                    "Не удалось отправить файл на обработку. "
                    "Проверьте соединение и попробуйте снова.\n"
                    "Код события: BOT_BACKEND_UNAVAILABLE",
                )
                self._log_status(user_id, "backend_error", {"filename": name})
                return
            await status_msg.edit_text(self._format_response(result))
            self._log_status(user_id, "backend_done", {"request_id": result.get("request_id")})
            return

        status_msg = await self.bot.send_message(chat_id, f"Обрабатываю {len(files)} файлов отдельно…")
        for index, (name, content) in enumerate(files, start=1):
            try:
                await status_msg.edit_text(f"Файл {index}/{len(files)}. Отправляю на сервер…")
                self._log_status(user_id, "backend_sending", {"filename": name, "index": index})
                result = await send_file_to_backend(self._backend_url, name, content, user_id, chat_id)
                await status_msg.edit_text(
                    f"Файл {index}/{len(files)} обработан.\n{self._format_response(result)}"
                )
                self._log_status(user_id, "backend_done", {"request_id": result.get("request_id")})
            except Exception:  # noqa: BLE001
                logger.exception("Backend request failed")
                await self.bot.send_message(
                    chat_id,
                    "Не удалось отправить файл на обработку. "
                    "Проверьте соединение и попробуйте снова.\n"
                    "Код события: BOT_BACKEND_UNAVAILABLE",
                )
                self._log_status(user_id, "backend_error", {"filename": name, "index": index})

    async def _handle_pending_choice(self, message: Message, user_id: str) -> None:
        """Явный UI: после каждого файла показываем кнопки действия."""
        files = self._collect_pending_files(user_id)

        if not settings.enable_split_mode:
            await self._process_pending_as_batch_chat(message.chat.id, user_id)
            return

        if not files:
            await message.answer("Нет ожидающих файлов.")
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
            }
            self._media_groups[group_id] = entry
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
            for name, content in files:
                self._storage.store_pending_bytes(user_id=user_id, filename=name, content=content)
            self._pending_users.add(user_id)
            self._pending_chats[user_id] = chat_id
            await self._send_mode_keyboard_to_chat(chat_id, user_id)
            return

        status_msg = await self.bot.send_message(
            chat_id,
            f"Получено файлов в одном сообщении: {len(files)}. Обрабатываю объединением…",
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
            await status_msg.edit_text("Ошибка при обработке файлов.")
            await self.bot.send_message(
                chat_id,
                "Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова.\n"
                "Код события: BOT_BACKEND_UNAVAILABLE",
            )
            self._log_status(user_id or "unknown", "media_group_batch_error")
            return
        await status_msg.edit_text(self._format_response(result))
        self._log_status(user_id or "unknown", "media_group_batch_done", {"request_id": result.get("request_id")})

    async def _send_single_file_keyboard(self, message: Message, user_id: str) -> None:
        """Один файл в pending — показываем кнопку 'Обработать' и 'Ещё файл'."""
        text = "📄 Файл получен. Что делаем?"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Обработать", callback_data="mode:process")],
                [InlineKeyboardButton(text="📎 Добавить ещё", callback_data="mode:wait")],
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
        text = f"Получено файлов: {len(files)}. Выберите режим:"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Объединить", callback_data="mode:merge")],
                [InlineKeyboardButton(text="📎 Добавить ещё", callback_data="mode:wait")],
            ]
        )
        if user_id in self._pending_prompt:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=self._pending_prompt[user_id])
            except Exception:  # noqa: BLE001
                logger.debug("Failed to delete pending prompt for user_id=%s", user_id)
        sent = await self.bot.send_message(chat_id, text, reply_markup=keyboard)
        self._pending_prompt[user_id] = sent.message_id

    async def on_mode_choice(self, query: CallbackQuery) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        data = (query.data or "").strip().lower()
        await query.answer()

        if data.startswith("split:"):
            await self._handle_split_choice(query, data)
            return

        # "Добавить ещё" — просто убираем клавиатуру, ждём следующий файл
        if data == "mode:wait":
            await query.message.edit_text("Ок, жду ещё файлы. Отправляйте.")
            return

        if user_id not in self._pending_users:
            await query.message.answer(
                "Нет ожидающих файлов. Отправьте файлы заново.\n"
                "Код события: BOT_NO_PENDING"
            )
            return

        # Отменяем старый таймер, если вдруг остался
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()

        if data == "mode:process":
            status_message = query.message
            try:
                await status_message.edit_text("⏳ Отправляю на обработку…")
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
            await self._accept_pending_as_split(
                query.message,
                user_id,
                status_message=query.message,
            )
            self._log_status(user_id, "mode_selected", {"mode": "merge"})
            return
        await query.message.answer("Неизвестный выбор. Используйте кнопки.")

    async def _handle_split_choice(self, query: CallbackQuery, data: str) -> None:
        """Обрабатывает кнопки split-режима."""
        if not query.from_user:
            return
        user_id = str(query.from_user.id)

        if user_id not in self._split_users:
            await query.message.edit_text("Режим объединения не включен. Введите /split.")
            return

        if data == "split:wait":
            await self._update_split_prompt(query.message, user_id)
            return

        if data == "split:cancel":
            self._clear_split_dir(user_id)
            self._split_users.discard(user_id)
            self._split_prompt.pop(user_id, None)
            await query.message.edit_text(
                "Режим объединения отменен. Буфер очищен.",
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

        await query.message.answer("Неизвестный выбор. Используйте кнопки.")

    async def _update_split_prompt(self, message: Message, user_id: str) -> None:
        """Обновляет единое сообщение split-режима с кнопками."""
        count = len(self._collect_split_files(user_id))
        text, keyboard = self._build_split_prompt(count)
        message_id = self._split_prompt.get(user_id)
        if message_id:
            try:
                await self.bot.delete_message(chat_id=message.chat.id, message_id=message_id)
            except Exception:  # noqa: BLE001
                logger.debug("Split prompt not modified for user_id=%s", user_id)
        sent = await message.answer(text, reply_markup=keyboard)
        self._split_prompt[user_id] = sent.message_id

    async def _finalize_split(
        self,
        chat_id: int,
        user_id: str,
        status_message: Message | None = None,
    ) -> None:
        """Отправляет split-части на backend и редактирует статусное сообщение."""
        files = self._collect_split_files(user_id)
        if not files:
            if status_message:
                await status_message.edit_text(
                    "Пока нет файлов. Отправьте части.",
                    reply_markup=None,
                )
                await self._update_split_prompt(status_message, user_id)
            else:
                text, keyboard = self._build_split_prompt(0)
                sent = await self.bot.send_message(chat_id, text, reply_markup=keyboard)
                self._split_prompt[user_id] = sent.message_id
            return

        self._log_status(user_id, "split_finish_requested")
        status_msg = status_message
        if status_msg:
            try:
                await status_msg.edit_text("⏳ Отправляю на сервер…", reply_markup=None)
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
                chat_id, f"Собрано файлов: {len(files)}. Отправляю на сервер…"
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
            await status_msg.edit_text("Ошибка при обработке файлов.")
            await self.bot.send_message(
                chat_id,
                "Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова.\n"
                "Код события: BOT_BACKEND_UNAVAILABLE",
            )
            self._log_status(user_id, "backend_batch_error")
            return
        finally:
            self._clear_split_dir(user_id)
            self._split_users.discard(user_id)
            self._split_prompt.pop(user_id, None)

        await status_msg.edit_text(self._format_response(result), reply_markup=None)
        self._log_status(user_id, "backend_batch_done", {"request_id": result.get("request_id")})

    @staticmethod
    def _build_split_prompt(count: int) -> tuple[str, InlineKeyboardMarkup]:
        text = f"Добавлено файлов: {count}. Отправляйте части или завершите."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✖ Отменить", callback_data="split:cancel"),
                    InlineKeyboardButton(text="✅ Завершить", callback_data="split:done"),
                ],
                [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="split:wait")],
            ]
        )
        return text, keyboard

    def _reset_user_buffers(self, user_id: str) -> None:
        """Очищает pending/split состояния пользователя, чтобы не тянуть старые файлы."""
        self._clear_pending_dir(user_id)
        self._clear_split_dir(user_id)
        self._pending_users.discard(user_id)
        self._split_users.discard(user_id)
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        self._pending_prompt.pop(user_id, None)
        self._split_prompt.pop(user_id, None)

    def _collect_split_files(self, user_id: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_split_files(user_id)

    def _clear_split_dir(self, user_id: str) -> None:
        self._storage.clear_split_dir(user_id)

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
        - пользователю показываем короткий «Код заявки» вида HHMMSS_mmm,
          чтобы его было легко продиктовать/вставить.

        Логику форматирования держим в одном месте (app.utils.user_messages),
        чтобы бот и воркер писали одинаково.
        """

        return format_user_response(payload)
