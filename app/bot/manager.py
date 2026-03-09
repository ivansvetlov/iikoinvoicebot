"""Модуль управления Telegram-ботом и его обработчиками."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.services.user_store import get_iiko_credentials, get_pdf_mode, set_iiko_credentials, set_pdf_mode
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
        self._split_users: set[str] = set()
        self._split_dir = Path(__file__).resolve().parents[2] / "data" / "split"
        self._split_dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir = Path(__file__).resolve().parents[2] / "data" / "pending"
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        self._pending_users: set[str] = set()
        self._pending_tasks: dict[str, asyncio.Task] = {}
        self._pending_chats: dict[str, int] = {}
        self._pending_prompt: dict[str, int] = {}
        self._media_groups: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task] = {}
        self._rate_limits: dict[str, list[datetime]] = {}
        self._recent_hashes: dict[str, dict[str, datetime]] = {}
        logger.info("Bot manager initialized")
        self._cleanup_pending_dirs()

    async def run(self) -> None:
        """Запускает polling-цикл бота."""
        logger.info("Starting bot polling")
        await self.dp.start_polling(self.bot)

    def _register_handlers(self) -> None:
        """Регистрирует обработчики сообщений."""
        self.dp.message.register(self.start, CommandStart())
        self.dp.message.register(self.set_mode, Command("mode"))
        self.dp.message.register(self.start_split, Command("split"))
        self.dp.message.register(self.choose_batch, Command("multi"))
        self.dp.message.register(self.finish_split, Command("done"))
        self.dp.message.register(self.cancel_split, Command("cancel"))
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
        if get_iiko_credentials(user_id):
            await message.answer("Вы уже авторизованы в iiko. Можете отправлять накладные.")
            return
        await message.answer("Для работы с iiko нужна авторизация. Введите логин iiko:")
        self._auth_state[user_id] = "await_login"
        self._log_status(user_id, "auth_requested", {"message_id": message.message_id})

    async def set_mode(self, message: Message) -> None:
        """Меняет режим обработки PDF (fast/accurate)."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        text = (message.text or "").strip().lower()
        if text.startswith("/modefast"):
            mode = "fast"
        elif text.startswith("/modeaccurate"):
            mode = "accurate"
        else:
            parts = text.split()
            if len(parts) == 1:
                current = get_pdf_mode(user_id)
                await message.answer(
                    "Режим обработки PDF:\n"
                    f"Сейчас: {current}\n"
                    "fast — быстрее и дешевле, но может пропускать строки.\n"
                    "accurate — точнее, но дороже.\n"
                    "Команды: /modefast или /modeaccurate."
                )
                return
            mode = parts[1].strip().lower()
            if mode not in {"fast", "accurate"}:
                await message.answer("Неверный режим. Используйте /modefast или /modeaccurate.")
                return
        set_pdf_mode(user_id, mode)
        await message.answer(f"Готово. Режим PDF: {mode}.")

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
            if text in {"multi", "раздельно", "много", "m"}:
                await self._process_pending_as_batch(message, user_id)
                self._log_status(user_id, "mode_selected", {"mode": "multi"})
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
        await message.answer(
            "Режим объединения включен. Отправляйте части накладной. "
            "Когда закончите — отправьте /done. Для отмены — /cancel."
        )
        self._log_status(user_id, "split_started")

    async def choose_batch(self, message: Message) -> None:
        """Обрабатывает ожидающие файлы как отдельные накладные."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        if user_id not in self._pending_users:
            await message.answer("Нет ожидающих файлов. Отправьте файлы и выберите режим.")
            return
        await self._process_pending_as_batch(message, user_id)

    async def finish_split(self, message: Message) -> None:
        """Завершает режим сплит и отправляет все части на обработку."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        if user_id not in self._split_users:
            await message.answer("Режим объединения не включен. Введите /split для начала.")
            return
        self._log_status(user_id, "split_finish_requested")
        files = self._collect_split_files(user_id)
        if not files:
            await message.answer("Нет файлов для обработки. Отправьте части и снова /done.")
            return
        status_msg = await message.answer(f"Собрано файлов: {len(files)}. Отправляю на сервер…")
        try:
            await status_msg.edit_text("Идет обработка объединенной накладной…")
            self._log_status(user_id, "backend_batch_sending", {"count": len(files)})
            result = await self._send_batch_to_backend(
                files,
                user_id,
                message.chat.id,
                status_message_id=status_msg.message_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Backend batch request failed")
            await status_msg.edit_text("Ошибка при обработке файлов.")
            await message.answer(
                "Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова."
            )
            self._log_status(user_id, "backend_batch_error")
            return
        finally:
            self._clear_split_dir(user_id)
            self._split_users.discard(user_id)

        await status_msg.edit_text(self._format_response(result))
        self._log_status(user_id, "backend_batch_done", {"request_id": result.get("request_id")})

    async def cancel_split(self, message: Message) -> None:
        """Отменяет режим сплит и очищает буфер."""
        if not message.from_user:
            return
        user_id = str(message.from_user.id)
        self._clear_split_dir(user_id)
        self._split_users.discard(user_id)
        await message.answer("Режим объединения отменен. Буфер очищен.")
        self._log_status(user_id, "split_cancelled")

    async def _send_to_backend(
        self,
        filename: str,
        content: bytes,
        user_id: str | None,
        chat_id: int | None,
        status_message_id: int | None = None,
    ) -> dict:
        """Отправляет файл в backend и возвращает JSON-ответ."""
        logger.info("Sending file to backend: %s", filename)
        async with httpx.AsyncClient(timeout=300) as client:
            for attempt in range(3):
                try:
                    data = {
                        "push_to_iiko": "true" if settings.push_to_iiko else "false",
                    }
                    if user_id:
                        data["user_id"] = user_id
                        data["pdf_mode"] = get_pdf_mode(user_id)
                    if chat_id:
                        data["chat_id"] = str(chat_id)
                    if status_message_id:
                        data["status_message_id"] = str(status_message_id)
                    response = await client.post(
                        f"{self._backend_url}/process",
                        files={"file": (filename, content)},
                        data=data,
                    )
                    try:
                        return response.json()
                    except ValueError:
                        response.raise_for_status()
                        raise
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    logger.warning("Backend unavailable, attempt %s", attempt + 1)
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt)
                        continue
                    raise exc
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    logger.warning("Backend status error: %s", status_code)
                    # 413 - payload too large
                    if status_code == 413:
                        return {
                            "status": "error",
                            "message": f"Файл слишком большой. Максимум {settings.max_upload_mb} MB.",
                        }
                    # 422 - validation
                    if status_code == 422:
                        return {
                            "status": "error",
                            "message": "Не удалось обработать запрос. Проверьте файл и попробуйте снова.",
                        }
                    # 429 - rate limit
                    if status_code == 429:
                        return {
                            "status": "error",
                            "message": "Сервис перегружен. Попробуйте отправить файл чуть позже.",
                        }
                    # прочие коды
                    return {
                        "status": "error",
                        "message": "Сервер временно недоступен. Попробуйте позже.",
                    }

    async def _send_batch_to_backend(
        self,
        files: list[tuple[str, bytes]],
        user_id: str | None,
        chat_id: int | None,
        status_message_id: int | None = None,
    ) -> dict:
        """Отправляет несколько файлов одной накладной в backend."""
        logger.info("Sending batch to backend: %s files", len(files))
        async with httpx.AsyncClient(timeout=300) as client:
            for attempt in range(3):
                try:
                    data = {
                        "push_to_iiko": "true" if settings.push_to_iiko else "false",
                    }
                    if user_id:
                        data["user_id"] = user_id
                        data["pdf_mode"] = get_pdf_mode(user_id)
                    if chat_id:
                        data["chat_id"] = str(chat_id)
                    if status_message_id:
                        data["status_message_id"] = str(status_message_id)
                    payload = [("files", (name, content)) for name, content in files]
                    response = await client.post(
                        f"{self._backend_url}/process-batch",
                        files=payload,
                        data=data,
                    )
                    try:
                        return response.json()
                    except ValueError:
                        response.raise_for_status()
                        raise
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    logger.warning("Backend unavailable, attempt %s", attempt + 1)
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt)
                        continue
                    raise exc

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
                "Если нужно срочно — отправьте позже."
            )
            self._log_status(user_id, "rate_limited")
            return
        if user_id in self._split_users:
            await self._store_split_file(document, filename or "invoice.bin", user_id)
            await message.answer("Файл добавлен в сплит. Отправьте /done, когда все части будут готовы.")
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
                "Если нужно срочно — отправьте позже."
            )
            self._log_status(user_id, "rate_limited")
            return
        if user_id in self._split_users:
            largest = photo_list[-1]
            file = await self.bot.get_file(largest.file_id)
            data = await self.bot.download_file(file.file_path)
            content = data.read()
            await self._store_split_bytes("invoice_photo.jpg", content, user_id)
            await message.answer("Фото добавлено в сплит. Отправьте /done, когда все части будут готовы.")
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
        user_dir = self._split_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_name = Path(filename).name
        target = user_dir / f"{stamp}_{safe_name}"
        target.write_bytes(content)

    async def _store_pending_file(self, document, filename: str, user_id: str) -> None:
        file = await self.bot.get_file(document.file_id)
        data = await self.bot.download_file(file.file_path)
        content = data.read()
        await self._store_pending_bytes(filename, content, user_id)

    async def _store_pending_bytes(self, filename: str, content: bytes, user_id: str) -> None:
        user_dir = self._pending_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_name = Path(filename).name
        target = user_dir / f"{stamp}_{safe_name}"
        target.write_bytes(content)

    def _collect_pending_files(self, user_id: str) -> list[tuple[str, bytes]]:
        user_dir = self._pending_dir / user_id
        if not user_dir.exists():
            return []
        files: list[tuple[str, bytes]] = []
        for path in sorted(user_dir.glob("*")):
            if path.is_file():
                files.append((path.name, path.read_bytes()))
        return files

    def _clear_pending_dir(self, user_id: str) -> None:
        user_dir = self._pending_dir / user_id
        if not user_dir.exists():
            return
        for path in user_dir.glob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to remove pending file")

    async def _accept_pending_as_split(self, message: Message, user_id: str) -> None:
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
        await message.answer(
            "Файлы перенесены в объединение. "
            "Отправляйте следующие части и затем /done."
        )

    async def _process_pending_as_batch(self, message: Message, user_id: str) -> None:
        await self._process_pending_as_batch_chat(message.chat.id, user_id)

    async def _process_pending_as_batch_chat(self, chat_id: int, user_id: str) -> None:
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
            status_msg = await self.bot.send_message(chat_id, "Файл получен. Отправляю на сервер…")
            try:
                await status_msg.edit_text("Файл на сервере. Идет обработка…")
                self._log_status(user_id, "backend_sending", {"filename": name})
                result = await self._send_to_backend(
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
                    "Проверьте соединение и попробуйте снова.",
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
                result = await self._send_to_backend(name, content, user_id, chat_id)
                await status_msg.edit_text(
                    f"Файл {index}/{len(files)} обработан.\n{self._format_response(result)}"
                )
                self._log_status(user_id, "backend_done", {"request_id": result.get("request_id")})
            except Exception:  # noqa: BLE001
                logger.exception("Backend request failed")
                await self.bot.send_message(
                    chat_id,
                    "Не удалось отправить файл на обработку. "
                    "Проверьте соединение и попробуйте снова.",
                )
                self._log_status(user_id, "backend_error", {"filename": name, "index": index})

    async def _handle_pending_choice(self, message: Message, user_id: str) -> None:
        files = self._collect_pending_files(user_id)
        if files and self._is_duplicate(user_id, files[-1][1]):
            await message.answer("Этот файл уже был отправлен. Пропускаю повтор.")
            self._log_status(user_id, "duplicate_skipped")
            return

        if not settings.enable_split_mode:
            await self._process_pending_as_batch_chat(message.chat.id, user_id)
            return

        if len(files) <= 1:
            await self._process_pending_as_batch_chat(message.chat.id, user_id)
            return

        if user_id not in self._pending_users:
            self._pending_users.add(user_id)
            self._pending_chats[user_id] = message.chat.id
            self._pending_tasks[user_id] = asyncio.create_task(self._auto_process_pending(user_id))

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
        status_msg = await self.bot.send_message(
            chat_id,
            f"Получено файлов в одном сообщении: {len(files)}. Обрабатываю объединением…",
        )
        try:
            self._log_status(user_id or "unknown", "media_group_batch_sending", {"count": len(files)})
            result = await self._send_batch_to_backend(
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
                "Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова.",
            )
            self._log_status(user_id or "unknown", "media_group_batch_error")
            return
        await status_msg.edit_text(self._format_response(result))
        self._log_status(user_id or "unknown", "media_group_batch_done", {"request_id": result.get("request_id")})

    async def _send_mode_keyboard(self, message: Message) -> None:
        text = "Выберите режим обработки (если не выбрать — через 30 сек будет 'Раздельно'):"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Объединить", callback_data="mode:merge")],
                [InlineKeyboardButton(text="Раздельно", callback_data="mode:multi")],
            ]
        )
        user_id = str(message.from_user.id) if message.from_user else None
        if user_id and user_id in self._pending_prompt:
            try:
                await self.bot.edit_message_text(
                    text=text,
                    chat_id=message.chat.id,
                    message_id=self._pending_prompt[user_id],
                    reply_markup=keyboard,
                )
                return
            except Exception:  # noqa: BLE001
                logger.exception("Failed to edit pending prompt")
        sent = await message.answer(text, reply_markup=keyboard)
        if user_id:
            self._pending_prompt[user_id] = sent.message_id

    async def on_mode_choice(self, query: CallbackQuery) -> None:
        if not query.from_user:
            return
        user_id = str(query.from_user.id)
        data = (query.data or "").strip().lower()
        await query.answer()
        if user_id not in self._pending_users:
            await query.message.answer("Нет ожидающих файлов. Отправьте файлы заново.")
            return
        task = self._pending_tasks.pop(user_id, None)
        if task:
            task.cancel()
        if data == "mode:merge":
            await self._accept_pending_as_split(query.message, user_id)
            self._log_status(user_id, "mode_selected", {"mode": "merge"})
            return
        if data == "mode:multi":
            await self._process_pending_as_batch_chat(query.message.chat.id, user_id)
            self._log_status(user_id, "mode_selected", {"mode": "multi"})
            return
        await query.message.answer("Неизвестный выбор. Используйте кнопки.")

    async def _auto_process_pending(self, user_id: str) -> None:
        await asyncio.sleep(30)
        if user_id not in self._pending_users:
            return
        chat_id = self._pending_chats.get(user_id)
        if not chat_id:
            return
        await self.bot.send_message(chat_id, "Время ожидания истекло. Обрабатываю раздельно.")
        await self._process_pending_as_batch_chat(chat_id, user_id)
        self._pending_tasks.pop(user_id, None)
        self._pending_prompt.pop(user_id, None)

    def _collect_split_files(self, user_id: str) -> list[tuple[str, bytes]]:
        user_dir = self._split_dir / user_id
        if not user_dir.exists():
            return []
        files: list[tuple[str, bytes]] = []
        for path in sorted(user_dir.glob("*")):
            if path.is_file():
                files.append((path.name, path.read_bytes()))
        return files

    def _clear_split_dir(self, user_id: str) -> None:
        user_dir = self._split_dir / user_id
        if not user_dir.exists():
            return
        for path in user_dir.glob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to remove split file")

    def _log_status(self, user_id: str, event: str, extra: dict | None = None) -> None:
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user_id": user_id,
            "event": event,
            "extra": extra or {},
        }
        try:
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
