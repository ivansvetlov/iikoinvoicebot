"""MAX invoice bot — main port of Telegram manager logic."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from maxapi import Bot, Dispatcher
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters.command import Command
from maxapi.types.message import Message
from maxapi.types.updates import BotStarted, MessageCallback, MessageCreated

from app.bot.backend_client import (
    send_batch_to_backend,
    send_file_to_backend,
    send_request_to_iiko,
    sync_nomenclature_request,
)
from app.bot.event_codes import (
    BOT_BACKEND_UNAVAILABLE,
    BOT_NO_PENDING,
    BOT_RATE_LIMIT,
    event_meta,
    with_event_code,
)
from app.bot.file_storage import PendingSplitStorage
from app.bot.invoice_keyboards import (
    build_back_confirm_actions,
    build_invoice_actions,
    build_posting_review_actions,
    build_service_menu_actions,
    build_sync_confirm_actions,
)
from app.bot.invoice_posting import (
    append_sync_note,
    count_posting_rows,
    format_posting_review_text,
    format_sync_note,
)
from app.bot.messages import Msg, pdf_mode_label
from app.config import settings as app_settings
from app.iiko.server_client import IikoServerClient
from app.services.user_store import (
    clear_iiko_credentials,
    get_iiko_credentials,
    get_pdf_mode,
    set_iiko_credentials,
    set_pdf_mode,
)
from app.task_store import (
    get_user_active_snapshot,
    get_user_last_task,
    reap_stale_tasks,
)
from app.utils.user_messages import format_invoice_markdown, format_user_response, short_request_code
from experiments.grok_telegram_bridge.security import is_allowed
from experiments.max_invoice_bot.attachments import download_from_message, has_downloadable_attachments
from experiments.max_invoice_bot.config import settings
from experiments.max_invoice_bot.edit_state import EditState
from experiments.max_invoice_bot.keyboards import dict_to_markup
from experiments.max_invoice_bot.messaging import (
    callback_update,
    dismiss_message,
    edit_message,
    prepare_outgoing_text,
    reply_or_edit,
    send_to_user,
)

PENDING_BURST_DEBOUNCE_SEC = 2.5

from experiments.max_invoice_bot.task_watcher import schedule_watch
from experiments.max_invoice_bot.user_ids import storage_dir_key, store_user_id

logger = logging.getLogger(__name__)

HTML = ParseMode.HTML
INFO_FIELDS = Msg.INFO_FIELDS
ITEM_FIELDS = Msg.ITEM_FIELDS
REQUESTS_DIR = Path(__file__).resolve().parents[2] / "logs" / "requests"
JOBS_DIR = Path(__file__).resolve().parents[2] / "data" / "jobs"



def _sender_id(event: MessageCreated | MessageCallback | BotStarted) -> int | None:
    if isinstance(event, BotStarted):
        return event.user.user_id
    if isinstance(event, MessageCallback):
        return event.callback.user.user_id
    if event.message.sender:
        return event.message.sender.user_id
    return None


def _auth_failure_message(exc: Exception) -> str:
    text = str(exc or "").strip()
    if "IIKO_API_BASE_URL is not configured" in text:
        return Msg.AUTH_API_NOT_CONFIGURED
    if any(
        token in text
        for token in ("getaddrinfo", "Name or service not known", "nodename nor servname", "ConnectError")
    ):
        return Msg.AUTH_NETWORK_ERROR
    return Msg.AUTH_FAILED


def _message_mid(message: Message) -> str | None:
    body = message.body
    if body and body.mid:
        return str(body.mid)
    return None


def _chat_id(message: Message) -> int | None:
    if message.recipient:
        return message.recipient.chat_id
    return None


def _button(text: str, callback_data: str, *, style: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text, "callback_data": callback_data}
    if style:
        payload["style"] = style
    return payload


class MaxInvoiceBot:
    """MAX port of invoice bot (Telegram manager.py as specification)."""

    def __init__(self) -> None:
        if not settings.max_invoice_bot_token:
            raise RuntimeError("MAX_INVOICE_BOT_TOKEN is not set")
        self.allowed = settings.allowed_ids()
        self._backend_url = settings.backend_url
        self.bot = Bot(settings.max_invoice_bot_token, parse_mode=HTML)
        self.dp = Dispatcher()
        self._iiko_client = IikoServerClient()

        base_data_dir = Path(__file__).resolve().parents[2] / "data"
        self._storage = PendingSplitStorage(base_data_dir=base_data_dir)
        self._storage.cleanup_old()

        self._auth_state: dict[str, str] = {}
        self._pending_login: dict[str, str] = {}
        self._split_users: set[str] = set()
        self._pending_users: set[str] = set()
        self._pending_prompt: dict[str, str] = {}
        self._pending_chats: dict[str, int] = {}
        self._pending_burst_ctx: dict[str, dict[str, Any]] = {}
        self._pending_burst_tasks: dict[str, asyncio.Task[None]] = {}
        self._split_prompt: dict[str, str] = {}
        self._status_prompt: dict[str, str] = {}
        self._rate_limits: dict[str, list[datetime]] = {}
        self._recent_hashes: dict[str, dict[str, datetime]] = {}
        self._iiko_send_inflight: set[str] = set()
        self._edit_state: dict[str, EditState] = {}

        self._register()
        logger.info("MaxInvoiceBot initialized")

    def _register(self) -> None:
        self.dp.bot_started.register(self.on_bot_started)
        self.dp.message_created.register(self.cmd_start, Command("start"))
        self.dp.message_created.register(self.cmd_status, Command("status"))
        self.dp.message_created.register(self.cmd_split, Command("split"))
        self.dp.message_created.register(self.cmd_done, Command("done"))
        self.dp.message_created.register(self.cmd_cancel, Command("cancel"))
        self.dp.message_callback.register(self.on_callback)
        self.dp.message_created.register(self.on_message)

    @staticmethod
    def _uid(max_user_id: int) -> str:
        return store_user_id(max_user_id)

    async def _deny_message(self, event: MessageCreated) -> None:
        await event.message.answer(Msg.ACCESS_DENIED, format=HTML)

    async def _deny_callback(self, event: MessageCallback) -> None:
        await event.ack(notification=Msg.ACCESS_DENIED)

    async def _answer(
        self,
        message: Message,
        text: str,
        keyboard: dict[str, Any] | None = None,
    ) -> Message:
        attachments = dict_to_markup(keyboard)
        kw: dict[str, Any] = {"format": HTML}
        if attachments is not None:
            kw["attachments"] = attachments
        try:
            sent = await message.answer(prepare_outgoing_text(text), **kw)
        except Exception:
            logger.exception("Failed to answer message")
            raise
        if sent and getattr(sent, "message", None):
            return sent.message
        return message

    def _format_response(self, payload: dict[str, Any]) -> str:
        return format_user_response(payload)

    def _load_request_payload(self, request_id: str) -> dict[str, Any] | None:
        path = REQUESTS_DIR / f"{request_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_request_payload(self, request_id: str, payload: dict[str, Any]) -> None:
        path = REQUESTS_DIR / f"{request_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _job_payload_path(request_id: str) -> Path:
        return JOBS_DIR / request_id / "payload.json"

    def _check_rate_limit(self, store_key: str | None) -> bool:
        if not store_key:
            return True
        now = datetime.now()
        window = now - timedelta(minutes=1)
        history = self._rate_limits.get(store_key, [])
        history = [ts for ts in history if ts > window]
        history.append(now)
        self._rate_limits[store_key] = history
        return len(history) <= app_settings.max_files_per_minute

    def _is_duplicate(self, store_key: str | None, content: bytes) -> bool:
        if not store_key:
            return False
        digest = hashlib.sha256(content).hexdigest()
        now = datetime.now()
        bucket = self._recent_hashes.get(store_key, {})
        cutoff = now - timedelta(minutes=10)
        bucket = {k: v for k, v in bucket.items() if v > cutoff}
        if digest in bucket:
            self._recent_hashes[store_key] = bucket
            return True
        bucket[digest] = now
        self._recent_hashes[store_key] = bucket
        return False

    @staticmethod
    def _pending_dir_key(store_key: str) -> str:
        return storage_dir_key(store_key)

    def _collect_pending_files(self, store_key: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_pending_files(self._pending_dir_key(store_key))

    def _collect_split_files(self, store_key: str) -> list[tuple[str, bytes]]:
        return self._storage.collect_split_files(self._pending_dir_key(store_key))

    def _clear_pending_dir(self, store_key: str) -> None:
        self._storage.clear_pending_dir(self._pending_dir_key(store_key))

    def _clear_split_dir(self, store_key: str) -> None:
        self._storage.clear_split_dir(self._pending_dir_key(store_key))

    def _deduplicate_pending_dir(self, store_key: str) -> dict[str, int]:
        return self._storage.deduplicate_pending_files(self._pending_dir_key(store_key))

    def _deduplicate_split_dir(self, store_key: str) -> dict[str, int]:
        return self._storage.deduplicate_split_files(self._pending_dir_key(store_key))

    def _pending_duplicates_count(self, store_key: str) -> int:
        return self._storage.count_pending_duplicates(self._pending_dir_key(store_key))

    def _split_duplicates_count(self, store_key: str) -> int:
        return self._storage.count_split_duplicates(self._pending_dir_key(store_key))

    def _store_pending_bytes(self, store_key: str, filename: str, content: bytes) -> bool:
        is_dup = self._is_duplicate(store_key, content)
        self._storage.store_pending_bytes(
            user_id=self._pending_dir_key(store_key),
            filename=filename,
            content=content,
        )
        return is_dup

    def _store_split_bytes(self, store_key: str, filename: str, content: bytes) -> bool:
        is_dup = self._is_duplicate(store_key, content)
        self._storage.store_split_bytes(
            user_id=self._pending_dir_key(store_key),
            filename=filename,
            content=content,
        )
        return is_dup

    def _ensure_pending_user(self, store_key: str) -> bool:
        if store_key in self._pending_users:
            return True
        if not self._collect_pending_files(store_key):
            return False
        self._pending_users.add(store_key)
        return True

    def _reset_user_buffers(self, store_key: str) -> None:
        self._cancel_pending_burst(store_key)
        self._clear_pending_dir(store_key)
        self._clear_split_dir(store_key)
        self._pending_users.discard(store_key)
        self._split_users.discard(store_key)
        self._pending_prompt.pop(store_key, None)
        self._pending_chats.pop(store_key, None)
        self._pending_burst_ctx.pop(store_key, None)
        self._split_prompt.pop(store_key, None)

    def _cancel_pending_burst(self, store_key: str) -> None:
        task = self._pending_burst_tasks.pop(store_key, None)
        if task and not task.done():
            task.cancel()

    @staticmethod
    def _sent_mid(sent: Any) -> str | None:
        if sent is None:
            return None
        msg = getattr(sent, "message", None) or sent
        return _message_mid(msg)

    async def _dismiss_message_by_id(self, message_id: str) -> None:
        with suppress(Exception):
            old_msg = await self.bot.get_message(message_id=message_id)
            if old_msg:
                await dismiss_message(old_msg)

    async def _upsert_prompt_card(
        self,
        *,
        store_key: str,
        prompt_map: dict[str, str],
        text: str,
        keyboard: dict[str, Any] | None,
        chat_id: int | None,
        user_id: int,
    ) -> None:
        old_mid = prompt_map.get(store_key)
        if old_mid:
            try:
                old_msg = await self.bot.get_message(message_id=old_mid)
                if old_msg:
                    await edit_message(old_msg, text, keyboard)
                    return
            except Exception:
                logger.debug("Prompt card edit failed for %s, replacing", store_key)
                await self._dismiss_message_by_id(old_mid)

        sent = await send_to_user(
            self.bot,
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            keyboard=keyboard,
        )
        mid = self._sent_mid(sent)
        if mid:
            prompt_map[store_key] = mid

    def _schedule_pending_burst(self, message: Message, store_key: str, max_uid: int) -> None:
        chat_id = _chat_id(message)
        if chat_id is not None:
            self._pending_chats[store_key] = chat_id
        self._pending_burst_ctx[store_key] = {
            "chat_id": chat_id,
            "max_uid": max_uid,
            "message": message,
        }
        self._ensure_pending_user(store_key)
        self._cancel_pending_burst(store_key)
        self._pending_burst_tasks[store_key] = asyncio.create_task(
            self._finalize_pending_burst(store_key)
        )

    async def _finalize_pending_burst(self, store_key: str) -> None:
        try:
            await asyncio.sleep(PENDING_BURST_DEBOUNCE_SEC)
        except asyncio.CancelledError:
            return
        finally:
            self._pending_burst_tasks.pop(store_key, None)

        if not self._collect_pending_files(store_key):
            return

        if not app_settings.enable_split_mode:
            ctx = self._pending_burst_ctx.get(store_key, {})
            anchor = ctx.get("message")
            if anchor is None:
                return
            await self._process_pending_as_batch(
                anchor,
                store_key,
                ctx.get("max_uid"),
            )
            return

        text, keyboard = self._build_pending_draft_content(store_key)
        ctx = self._pending_burst_ctx.get(store_key, {})
        await self._upsert_prompt_card(
            store_key=store_key,
            prompt_map=self._pending_prompt,
            text=text,
            keyboard=keyboard,
            chat_id=self._pending_chats.get(store_key) or ctx.get("chat_id"),
            user_id=int(ctx.get("max_uid") or 0),
        )

    def _build_pending_draft_content(self, store_key: str) -> tuple[str, dict[str, Any] | None]:
        files = self._collect_pending_files(store_key)
        duplicate_count = self._pending_duplicates_count(store_key)
        count = len(files)

        if count == 1 and any(name.lower().endswith(".pdf") for name, _ in files):
            current = pdf_mode_label(get_pdf_mode(store_key))
            text = Msg.PDF_MODE.format(current=current)
            keyboard = {
                "inline_keyboard": [
                    [_button(Msg.BTN_FAST, "pdf:fast", style="primary")],
                    [_button(Msg.BTN_ACCURATE, "pdf:accurate")],
                ]
            }
            return text, keyboard

        if count == 1:
            text = Msg.PENDING_SINGLE
            keyboard = {
                "inline_keyboard": [
                    [_button(Msg.BTN_PROCESS_NOW, "mode:process", style="primary")],
                ]
            }
            return text, keyboard

        text = Msg.PENDING_MULTI.format(count=count)
        if duplicate_count > 0:
            text += Msg.PENDING_DUPS.format(count=duplicate_count)
        rows = [[_button(Msg.BTN_MERGE_SEND, "mode:merge", style="success")]]
        if duplicate_count > 0:
            rows.append([_button(Msg.BTN_DEDUP, "mode:dedup", style="danger")])
        return text, {"inline_keyboard": rows}

    def _auth_already_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [_button(Msg.BTN_AUTH_SWITCH, "auth:switch", style="danger")],
            ]
        }

    def _status_keyboard(self, retry_request_id: str | None = None) -> dict[str, Any]:
        rows = [[_button(Msg.BTN_STATUS_REFRESH, "status:refresh")]]
        if retry_request_id:
            rows.append(
                [_button(Msg.BTN_STATUS_RETRY, f"status:retry:{retry_request_id}", style="primary")]
            )
        return {"inline_keyboard": rows}

    def _status_retry_request_id(self, store_key: str) -> str | None:
        last = get_user_last_task(store_key)
        if not last:
            return None
        if str(last.get("status") or "") != "error":
            return None
        request_id = str(last.get("request_id") or "")
        if not request_id:
            return None
        if not self._job_payload_path(request_id).exists():
            return None
        return request_id

    def _build_status_text(self, store_key: str) -> str:
        reaped = 0
        if app_settings.status_auto_reap:
            reaped = reap_stale_tasks(
                user_id=store_key,
                stale_minutes=app_settings.status_stale_minutes,
            )
        snapshot = {"queued": 0, "processing": 0, "stale": 0}
        for row in get_user_active_snapshot(store_key) or []:
            status = str(row.get("status") or "")
            if status in snapshot:
                snapshot[status] += 1
        last = get_user_last_task(store_key)
        pending_count = len(self._collect_pending_files(store_key))

        lines = [
            Msg.STATUS_TITLE,
            Msg.STATUS_SCOPE.format(hours=app_settings.status_active_hours),
            "",
        ]
        if reaped > 0:
            lines.append(Msg.STATUS_REAPED.format(count=reaped))
        lines.append(Msg.STATUS_QUEUE.format(queued=snapshot.get("queued", 0)))
        lines.append(Msg.STATUS_PROCESSING.format(processing=snapshot.get("processing", 0)))
        if snapshot.get("stale", 0) > 0:
            lines.append(Msg.STATUS_STALE.format(stale=snapshot.get("stale", 0)))
            lines.append(Msg.STATUS_STALE_HINT)

        if pending_count > 0:
            lines.append("")
            lines.append(Msg.STATUS_PENDING.format(count=pending_count))

        if last:
            code = short_request_code(last.get("request_id")) or (last.get("request_id") or "—")
            status_raw = str(last.get("status") or "")
            status_human = Msg.STATUS_STATE_MAP.get(status_raw, status_raw or "unknown")
            lines.append("")
            lines.append(Msg.STATUS_LAST_REQUEST.format(code=code))
            lines.append(Msg.STATUS_LAST_STATE.format(status=status_human))
            last_message = (last.get("message") or "").strip()
            if last_message:
                lines.append(Msg.STATUS_LAST_MESSAGE.format(message=last_message))
        elif pending_count == 0:
            lines.append("")
            lines.append(Msg.STATUS_EMPTY)

        return "\n".join(lines).strip()

    async def _deliver_backend_result(
        self,
        result: dict[str, Any],
        status_msg: Message,
        *,
        max_user_id: int,
        chat_id: int | None,
    ) -> None:
        status = str(result.get("status") or "").lower()
        request_id = str(result.get("request_id") or "")

        if status == "error":
            await reply_or_edit(status_msg, self._format_response(result))
            return

        if status == "queued" and request_id:
            await reply_or_edit(status_msg, self._format_response(result))
            schedule_watch(
                self.bot,
                chat_id=chat_id,
                max_user_id=max_user_id,
                request_id=request_id,
                status_message_id=_message_mid(status_msg),
            )
            return

        if status == "ok":
            text = format_invoice_markdown(result)
            allow_send = not bool(result.get("iiko_uploaded"))
            allow_sync = not bool(result.get("nomenclature_synced"))
            keyboard = build_invoice_actions(
                request_id or result.get("request_id"),
                allow_send=allow_send,
                allow_sync=allow_sync,
            )
            await reply_or_edit(status_msg, text, keyboard)
            return

        await reply_or_edit(status_msg, self._format_response(result))

    def _prepare_auth_start(self, store_key: str) -> tuple[str, dict[str, Any] | None]:
        self._reset_user_buffers(store_key)
        if get_iiko_credentials(store_key):
            return Msg.AUTH_ALREADY, self._auth_already_keyboard()
        self._auth_state[store_key] = "await_login"
        return Msg.AUTH_START, None

    async def on_bot_started(self, event: BotStarted) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            return
        store_key = self._uid(max_uid)
        text, keyboard = self._prepare_auth_start(store_key)
        await send_to_user(
            self.bot,
            chat_id=event.chat_id,
            user_id=max_uid,
            text=text,
            keyboard=keyboard,
        )

    async def cmd_start(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return
        store_key = self._uid(max_uid)
        text, keyboard = self._prepare_auth_start(store_key)
        await self._answer(event.message, text, keyboard)

    async def cmd_status(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return
        store_key = self._uid(max_uid)
        text = self._build_status_text(store_key)
        retry_id = self._status_retry_request_id(store_key)
        keyboard = self._status_keyboard(retry_id)
        old_mid = self._status_prompt.get(store_key)
        if old_mid:
            try:
                old_msg = await self.bot.get_message(message_id=old_mid)
                if old_msg:
                    await reply_or_edit(old_msg, text, keyboard)
                    return
            except Exception:
                logger.debug("Failed to edit status message for %s", store_key)
        sent = await self._answer(event.message, text, keyboard)
        mid = _message_mid(sent)
        if mid:
            self._status_prompt[store_key] = mid

    async def cmd_split(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return
        if not app_settings.enable_split_mode:
            await self._answer(event.message, Msg.SPLIT_DISABLED)
            return
        store_key = self._uid(max_uid)
        if not get_iiko_credentials(store_key):
            await self._answer(event.message, Msg.NO_IIKO_CREDENTIALS)
            return
        self._split_users.add(store_key)
        self._clear_split_dir(store_key)
        self._clear_pending_dir(store_key)
        self._pending_users.discard(store_key)
        self._pending_prompt.pop(store_key, None)
        await self._answer(event.message, Msg.SPLIT_ENABLED)

    async def cmd_done(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return
        store_key = self._uid(max_uid)
        if store_key not in self._split_users:
            await self._answer(event.message, Msg.SPLIT_NOT_ENABLED)
            return
        await self._answer(event.message, Msg.SPLIT_FINISHING)
        await self._finalize_split(event.message, store_key, max_uid, status_message=None)

    async def cmd_cancel(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return
        store_key = self._uid(max_uid)
        self._clear_split_dir(store_key)
        self._split_users.discard(store_key)
        self._split_prompt.pop(store_key, None)
        await self._answer(event.message, Msg.SPLIT_CANCELLED)

    async def on_message(self, event: MessageCreated) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_message(event)
            return

        message = event.message
        try:
            await self._on_message_body(message, max_uid)
        except Exception:
            logger.exception("on_message failed for user %s", max_uid)
            with suppress(Exception):
                await self._answer(message, Msg.HANDLER_ERROR)

    async def _on_message_body(self, message: Message, max_uid: int) -> None:
        body = message.body
        text = (body.text if body else "") or ""
        text = text.strip()

        if text.startswith("/"):
            return

        store_key = self._uid(max_uid)

        if has_downloadable_attachments(message):
            await self._handle_attachments(message, max_uid, store_key)
            return

        if not text:
            return

        if await self._handle_edit_text(message, store_key, text):
            return

        if store_key in self._pending_users and text.lower() in Msg.MERGE_ALIASES:
            await self._accept_pending_as_split(message, store_key, max_uid)
            return

        state = self._auth_state.get(store_key)
        if not state:
            await self._answer(message, Msg.ACCEPTS_FILES)
            return

        if state == "await_login":
            self._pending_login[store_key] = text
            self._auth_state[store_key] = "await_password"
            await self._answer(message, Msg.AUTH_PASSWORD)
            return

        if state == "await_password":
            login = self._pending_login.get(store_key)
            if not login:
                self._auth_state[store_key] = "await_login"
                await self._answer(message, Msg.AUTH_LOGIN_MISSING)
                return
            await self._answer(message, Msg.AUTH_CHECKING)
            try:
                await self._iiko_client.verify_credentials(login, text)
            except Exception as exc:
                logger.warning(
                    "iiko auth failed for %s (store=%s): %s",
                    login,
                    store_key,
                    exc,
                    exc_info=True,
                )
                self._auth_state[store_key] = "await_login"
                self._pending_login.pop(store_key, None)
                await self._answer(message, _auth_failure_message(exc))
                return
            set_iiko_credentials(store_key, login, text)
            self._auth_state.pop(store_key, None)
            self._pending_login.pop(store_key, None)
            await self._answer(message, Msg.AUTH_SAVED)
            return

        await self._answer(message, Msg.ACCEPTS_FILES)

    async def _handle_attachments(self, message: Message, max_uid: int, store_key: str) -> None:
        if not get_iiko_credentials(store_key):
            await self._answer(message, Msg.NO_IIKO_CREDENTIALS)
            return
        if not self._check_rate_limit(store_key):
            await self._answer(message, with_event_code(Msg.RATE_LIMIT, BOT_RATE_LIMIT))
            return

        files = await download_from_message(message, auth_token=settings.max_invoice_bot_token)
        if not files:
            await self._answer(message, Msg.ACCEPTS_ONLY_SUPPORTED)
            return

        max_bytes = app_settings.max_upload_mb * 1024 * 1024
        dup_count = 0

        for item in files:
            if len(item.content) > max_bytes:
                await self._answer(message, Msg.FILE_TOO_LARGE.format(max_mb=app_settings.max_upload_mb))
                return

        if store_key in self._split_users:
            for item in files:
                if self._store_split_bytes(store_key, item.filename, item.content):
                    dup_count += 1
            if dup_count:
                await self._notify_soft_duplicate(message, dup_count)
            await self._update_split_prompt(message, store_key)
            return

        for item in files:
            if self._store_pending_bytes(store_key, item.filename, item.content):
                dup_count += 1

        if dup_count and store_key in self._split_users:
            await self._notify_soft_duplicate(message, dup_count)

        if store_key in self._split_users:
            return

        self._schedule_pending_burst(message, store_key, max_uid)

    async def _notify_soft_duplicate(self, message: Message, duplicate_count: int) -> None:
        if duplicate_count <= 1:
            text = Msg.SOFT_DUP_ONE
        else:
            text = Msg.SOFT_DUP_MANY.format(count=duplicate_count)
        await self._answer(message, text)

    async def _refresh_pending_draft(self, message: Message, store_key: str) -> None:
        files = self._collect_pending_files(store_key)
        if not files:
            await self._answer(message, Msg.NO_PENDING)
            return
        if not app_settings.enable_split_mode:
            await self._process_pending_as_batch(message, store_key, _sender_id_from_message(message))
            return
        self._ensure_pending_user(store_key)
        text, keyboard = self._build_pending_draft_content(store_key)
        await self._upsert_prompt_card(
            store_key=store_key,
            prompt_map=self._pending_prompt,
            text=text,
            keyboard=keyboard,
            chat_id=_chat_id(message) or self._pending_chats.get(store_key),
            user_id=_sender_id_from_message(message) or 0,
        )

    def _build_split_prompt(self, store_key: str, count: int) -> tuple[str, dict[str, Any]]:
        duplicate_count = self._split_duplicates_count(store_key)
        text = Msg.SPLIT_PROMPT.format(count=count)
        if duplicate_count > 0:
            text += Msg.SPLIT_DUPS.format(count=duplicate_count)
        first_row = [_button(Msg.BTN_SPLIT_CANCEL, "split:cancel", style="danger")]
        if duplicate_count > 0:
            first_row.append(_button(Msg.BTN_DEDUP, "split:dedup", style="danger"))
        keyboard = {
            "inline_keyboard": [
                first_row,
                [_button(Msg.BTN_SPLIT_DONE, "split:done", style="success")],
            ]
        }
        return text, keyboard

    async def _update_split_prompt(self, message: Message, store_key: str) -> None:
        count = len(self._collect_split_files(store_key))
        text, keyboard = self._build_split_prompt(store_key, count)
        await self._upsert_prompt_card(
            store_key=store_key,
            prompt_map=self._split_prompt,
            text=text,
            keyboard=keyboard,
            chat_id=_chat_id(message) or self._pending_chats.get(store_key),
            user_id=_sender_id_from_message(message) or 0,
        )

    async def _accept_pending_as_split(self, message: Message, store_key: str, max_uid: int) -> None:
        files = self._collect_pending_files(store_key)
        if not files:
            await self._answer(message, Msg.NO_PENDING)
            self._pending_users.discard(store_key)
            return
        self._clear_split_dir(store_key)
        for name, content in files:
            self._store_split_bytes(store_key, name, content)
        self._clear_pending_dir(store_key)
        self._pending_users.discard(store_key)
        self._pending_prompt.pop(store_key, None)
        self._split_users.add(store_key)
        await self._update_split_prompt(message, store_key)

    async def _process_pending_as_batch(
        self,
        message: Message,
        store_key: str,
        max_uid: int | None,
        *,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(store_key)
        if not files:
            await self._answer(message, Msg.NO_PENDING)
            self._pending_users.discard(store_key)
            return

        self._clear_pending_dir(store_key)
        self._pending_users.discard(store_key)
        self._pending_prompt.pop(store_key, None)

        chat_id = _chat_id(message)
        max_uid = max_uid or (message.sender.user_id if message.sender else 0)

        if len(files) == 1:
            name, content = files[0]
            status_msg = status_message
            if status_msg:
                await reply_or_edit(status_msg, Msg.FILE_RECEIVED_SENDING)
            else:
                status_msg = await self._answer(message, Msg.FILE_RECEIVED_SENDING)
            await reply_or_edit(status_msg, Msg.FILE_ON_SERVER_PROCESSING)
            try:
                result = await send_file_to_backend(
                    self._backend_url,
                    name,
                    content,
                    store_key,
                    chat_id=None,
                    status_message_id=None,
                )
            except Exception:
                logger.exception("Backend request failed")
                await reply_or_edit(status_msg, Msg.BACKEND_FILE_ERROR)
                await send_to_user(
                    self.bot,
                    chat_id=chat_id,
                    user_id=max_uid,
                    text=with_event_code(Msg.BACKEND_SEND_FILE_FAILED, BOT_BACKEND_UNAVAILABLE),
                )
                return
            await self._deliver_backend_result(
                result,
                status_msg,
                max_user_id=max_uid,
                chat_id=chat_id,
            )
            return

        status_msg = status_message or await self._answer(
            message,
            Msg.PROCESSING_SEPARATELY.format(count=len(files)),
        )
        for index, (name, content) in enumerate(files, start=1):
            try:
                await reply_or_edit(
                    status_msg,
                    Msg.FILE_PROGRESS.format(index=index, total=len(files)),
                )
                result = await send_file_to_backend(
                    self._backend_url,
                    name,
                    content,
                    store_key,
                    chat_id=None,
                    status_message_id=None,
                )
                await reply_or_edit(
                    status_msg,
                    Msg.FILE_DONE.format(
                        index=index,
                        total=len(files),
                        result=self._format_response(result),
                    ),
                )
                if str(result.get("status") or "").lower() == "queued" and result.get("request_id"):
                    schedule_watch(
                        self.bot,
                        chat_id=chat_id,
                        max_user_id=max_uid,
                        request_id=str(result["request_id"]),
                        status_message_id=_message_mid(status_msg),
                    )
            except Exception:
                logger.exception("Backend request failed")
                await send_to_user(
                    self.bot,
                    chat_id=chat_id,
                    user_id=max_uid,
                    text=with_event_code(Msg.BACKEND_SEND_FILE_FAILED, BOT_BACKEND_UNAVAILABLE),
                )

    async def _process_pending_as_merged_batch(
        self,
        message: Message,
        store_key: str,
        max_uid: int,
        *,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_pending_files(store_key)
        if not files:
            await self._answer(message, Msg.NO_PENDING)
            self._pending_users.discard(store_key)
            return

        self._clear_pending_dir(store_key)
        self._pending_users.discard(store_key)
        self._pending_prompt.pop(store_key, None)

        status_msg = status_message
        if status_msg:
            await reply_or_edit(status_msg, Msg.BATCH_COLLECTED.format(count=len(files)))
        else:
            status_msg = await self._answer(message, Msg.BATCH_COLLECTED.format(count=len(files)))
        chat_id = _chat_id(message)
        try:
            result = await send_batch_to_backend(
                self._backend_url,
                files,
                store_key,
                chat_id=None,
                status_message_id=None,
            )
        except Exception:
            logger.exception("Backend batch request failed")
            await reply_or_edit(status_msg, Msg.BACKEND_FILES_ERROR)
            await send_to_user(
                self.bot,
                chat_id=chat_id,
                user_id=max_uid,
                text=with_event_code(Msg.BACKEND_SEND_FILES_FAILED, BOT_BACKEND_UNAVAILABLE),
            )
            return

        await self._deliver_backend_result(
            result,
            status_msg,
            max_user_id=max_uid,
            chat_id=chat_id,
        )

    async def _finalize_split(
        self,
        message: Message,
        store_key: str,
        max_uid: int,
        *,
        status_message: Message | None = None,
    ) -> None:
        files = self._collect_split_files(store_key)
        chat_id = _chat_id(message)

        if not files:
            if status_message:
                await reply_or_edit(status_message, Msg.SPLIT_EMPTY)
                await self._update_split_prompt(status_message, store_key)
            else:
                text, keyboard = self._build_split_prompt(store_key, 0)
                sent = await self._answer(message, text, keyboard)
                mid = _message_mid(sent)
                if mid:
                    self._split_prompt[store_key] = mid
            return

        status_msg = status_message
        if status_msg:
            await reply_or_edit(status_msg, Msg.SPLIT_SENDING)
        else:
            old_mid = self._split_prompt.get(store_key)
            if old_mid:
                await self._dismiss_message_by_id(old_mid)
                self._split_prompt.pop(store_key, None)
            status_msg = await self._answer(message, Msg.BATCH_COLLECTED.format(count=len(files)))

        try:
            result = await send_batch_to_backend(
                self._backend_url,
                files,
                store_key,
                chat_id=None,
                status_message_id=None,
            )
        except Exception:
            logger.exception("Backend split batch failed")
            await reply_or_edit(status_msg, Msg.BACKEND_FILES_ERROR)
            await send_to_user(
                self.bot,
                chat_id=chat_id,
                user_id=max_uid,
                text=with_event_code(Msg.BACKEND_SEND_FILES_FAILED, BOT_BACKEND_UNAVAILABLE),
            )
            return
        finally:
            self._clear_split_dir(store_key)
            self._split_users.discard(store_key)
            self._split_prompt.pop(store_key, None)

        await self._deliver_backend_result(
            result,
            status_msg,
            max_user_id=max_uid,
            chat_id=chat_id,
        )

    async def on_callback(self, event: MessageCallback) -> None:
        max_uid = _sender_id(event)
        if max_uid is None or not is_allowed(max_uid, self.allowed):
            await self._deny_callback(event)
            return

        data = (event.callback.payload or "").strip()
        store_key = self._uid(max_uid)
        message = event.message

        if data.startswith("auth:"):
            await self._handle_auth_choice(event, store_key, data)
            return
        if data.startswith("status:"):
            await self._handle_status_choice(event, store_key, data, max_uid)
            return
        if data.startswith("pdf:"):
            self._cancel_pending_burst(store_key)
            await self._handle_pdf_choice(event, store_key, data, max_uid)
            return
        if data.startswith("inv:"):
            await self._handle_invoice_actions(event, store_key, data, max_uid)
            return
        if data.startswith("edit:"):
            await self._handle_edit_actions(event, store_key, data)
            return
        if data.startswith("split:"):
            await self._handle_split_choice(event, store_key, data, max_uid)
            return
        if data.startswith("mode:"):
            self._cancel_pending_burst(store_key)
            await self._handle_mode_choice(event, store_key, data, max_uid)
            return

        await event.ack(notification=Msg.MODE_UNKNOWN)

    async def _handle_auth_choice(self, event: MessageCallback, store_key: str, data: str) -> None:
        if data == "auth:switch":
            self._reset_user_buffers(store_key)
            clear_iiko_credentials(store_key)
            self._pending_login.pop(store_key, None)
            self._auth_state[store_key] = "await_login"
            await callback_update(event, Msg.AUTH_SWITCHED)
            return
        await event.ack(notification=Msg.BAD_COMMAND)

    async def _handle_status_choice(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
        max_uid: int,
    ) -> None:
        if data == "status:refresh":
            text = self._build_status_text(store_key)
            keyboard = self._status_keyboard(self._status_retry_request_id(store_key))
            await callback_update(event, text, keyboard)
            mid = _message_mid(event.message)
            if mid:
                self._status_prompt[store_key] = mid
            return
        if data.startswith("status:retry:"):
            request_id = data.split(":", 2)[2]
            await self._retry_status_request(event.message, store_key, request_id, max_uid)
            return
        await event.ack(notification=Msg.BAD_COMMAND)

    async def _retry_status_request(
        self,
        message: Message,
        store_key: str,
        request_id: str,
        max_uid: int,
    ) -> None:
        payload_path = self._job_payload_path(request_id)
        keyboard = self._status_keyboard(self._status_retry_request_id(store_key))
        if not payload_path.exists():
            await reply_or_edit(message, Msg.STATUS_RETRY_SOURCE_MISSING, keyboard)
            return

        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception:
            await reply_or_edit(message, Msg.STATUS_RETRY_SOURCE_MISSING, keyboard)
            return

        payload_user_id = str(payload.get("user_id") or "")
        if payload_user_id and payload_user_id != store_key:
            await reply_or_edit(message, Msg.STATUS_RETRY_DENIED, keyboard)
            return

        chat_id = _chat_id(message)
        push_to_iiko = bool(payload.get("push_to_iiko", app_settings.push_to_iiko))

        try:
            if payload.get("files"):
                batch: list[tuple[str, bytes]] = []
                for name, path in payload["files"]:
                    batch.append((name, Path(path).read_bytes()))
                result = await send_batch_to_backend(
                    self._backend_url,
                    batch,
                    store_key,
                    chat_id=None,
                    status_message_id=None,
                    push_to_iiko_override=push_to_iiko,
                )
            else:
                filename = payload.get("filename")
                file_path = payload.get("file_path")
                if not filename or not file_path:
                    await reply_or_edit(message, Msg.STATUS_RETRY_SOURCE_MISSING, keyboard)
                    return
                result = await send_file_to_backend(
                    self._backend_url,
                    filename,
                    Path(file_path).read_bytes(),
                    store_key,
                    chat_id=None,
                    status_message_id=None,
                    push_to_iiko_override=push_to_iiko,
                )
        except Exception:
            logger.exception("Failed to retry request from status card")
            await reply_or_edit(message, Msg.STATUS_RETRY_FAILED, keyboard)
            return

        lines = [Msg.STATUS_RETRY_SENT, "", self._build_status_text(store_key)]
        await reply_or_edit(message, "\n".join(lines).strip(), keyboard)
        mid = _message_mid(message)
        if mid:
            self._status_prompt[store_key] = mid

        status = str(result.get("status") or "").lower()
        if status == "queued" and result.get("request_id"):
            schedule_watch(
                self.bot,
                chat_id=chat_id,
                max_user_id=max_uid,
                request_id=str(result["request_id"]),
                status_message_id=mid,
            )

    async def _handle_pdf_choice(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
        max_uid: int,
    ) -> None:
        if not self._ensure_pending_user(store_key):
            await callback_update(
                event,
                with_event_code(Msg.NO_PENDING_FILE_REUPLOAD, BOT_NO_PENDING),
            )
            return

        if data == "pdf:fast":
            set_pdf_mode(store_key, "fast")
            await callback_update(event, Msg.PDF_SET_FAST)
            await self._process_pending_as_batch(
                event.message,
                store_key,
                max_uid,
                status_message=event.message,
            )
            return
        if data == "pdf:accurate":
            set_pdf_mode(store_key, "accurate")
            await callback_update(event, Msg.PDF_SET_ACCURATE)
            await self._process_pending_as_batch(
                event.message,
                store_key,
                max_uid,
                status_message=event.message,
            )
            return
        await event.ack(notification=Msg.MODE_UNKNOWN)

    async def _handle_mode_choice(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
        max_uid: int,
    ) -> None:
        if data == "mode:wait":
            await callback_update(event, Msg.PENDING_WAIT)
            return

        if not self._ensure_pending_user(store_key):
            await callback_update(
                event,
                with_event_code(Msg.NO_PENDING_REUPLOAD, BOT_NO_PENDING),
            )
            return

        if data == "mode:process":
            await callback_update(event, Msg.SENDING_PROCESS)
            await self._process_pending_as_batch(
                event.message,
                store_key,
                max_uid,
                status_message=event.message,
            )
            return
        if data == "mode:merge":
            await callback_update(event, Msg.MERGING_SENDING)
            await self._process_pending_as_merged_batch(
                event.message,
                store_key,
                max_uid,
                status_message=event.message,
            )
            return
        if data == "mode:dedup":
            stats = self._deduplicate_pending_dir(store_key)
            draft_text, keyboard = self._build_pending_draft_content(store_key)
            dedup_note = Msg.DEDUP_DONE.format(removed=stats["removed"], kept=stats["kept"])
            await callback_update(event, f"{dedup_note}\n\n{draft_text}", keyboard)
            return
        await event.ack(notification=Msg.MODE_UNKNOWN)

    async def _handle_split_choice(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
        max_uid: int,
    ) -> None:
        if store_key not in self._split_users:
            await callback_update(event, Msg.SPLIT_NOT_ENABLED_SHORT)
            return

        if data == "split:wait":
            await callback_update(event, Msg.SPLIT_WAIT)
            return
        if data == "split:dedup":
            stats = self._deduplicate_split_dir(store_key)
            await callback_update(
                event,
                Msg.DEDUP_DONE.format(removed=stats["removed"], kept=stats["kept"]),
            )
            await self._update_split_prompt(event.message, store_key)
            return
        if data == "split:cancel":
            self._clear_split_dir(store_key)
            self._split_users.discard(store_key)
            self._split_prompt.pop(store_key, None)
            await callback_update(event, Msg.SPLIT_CANCEL_INFO)
            return
        if data == "split:done":
            await self._finalize_split(
                event.message,
                store_key,
                max_uid,
                status_message=event.message,
            )
            return
        await event.ack(notification=Msg.MODE_UNKNOWN)

    async def _handle_invoice_actions(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
        max_uid: int,
    ) -> None:
        parts = data.split(":")
        if len(parts) < 3:
            await event.ack(notification=Msg.BAD_COMMAND)
            return

        message = event.message

        if parts[1] == "service":
            await self._handle_service_action(event, store_key, parts[2:])
            return

        if parts[1] == "back" and len(parts) >= 3:
            request_id = parts[2]
            if len(parts) >= 4 and parts[3] == "stay":
                payload = self._load_request_payload(request_id)
                if payload:
                    await self._show_recognition_card(message, payload)
                return
            await self._show_back_confirm(message, request_id)
            return

        action, request_id = parts[1], parts[2]

        if action == "cancel":
            await self._show_back_confirm(message, request_id)
            self._edit_state.pop(store_key, None)
            return

        if action == "backconfirm":
            await reply_or_edit(message, Msg.BACK_CONFIRM_DONE)
            self._edit_state.pop(store_key, None)
            return

        if action == "edit":
            payload = self._load_request_payload(request_id)
            if not payload:
                await send_to_user(
                    self.bot,
                    chat_id=_chat_id(message),
                    user_id=max_uid,
                    text=Msg.EDIT_NOT_FOUND_REQUEST,
                )
                return
            state = EditState(request_id=request_id, payload=payload)
            self._edit_state[store_key] = state
            await self._show_edit_menu(message, state)
            return

        if action == "syncnom":
            await self._show_sync_confirm(message, request_id, store_key=store_key)
            return

        if action == "syncnomconfirm":
            await self._run_sync_nomenclature(message, request_id, store_key=store_key)
            return

        if action == "send":
            await self._show_posting_review(message, request_id, store_key=store_key)
            return

        if action == "postconfirm":
            _ready, blocked = self._posting_counts(request_id)
            if blocked > 0:
                await reply_or_edit(message, Msg.POSTING_BLOCKED.format(blocked=blocked))
                return
            await self._send_to_iiko(message, request_id, store_key=store_key)
            return

        if action == "refreshunits":
            await self._show_posting_review(
                message,
                request_id,
                store_key=store_key,
                refresh_units=True,
            )
            return

        if action == "retry":
            await self._retry_status_request(message, store_key, request_id, max_uid)
            return

    async def _handle_service_action(
        self,
        event: MessageCallback,
        store_key: str,
        tail: list[str],
    ) -> None:
        message = event.message
        max_uid = _sender_id(event) or 0
        if not tail:
            await event.ack(notification=Msg.BAD_COMMAND)
            return
        if len(tail) == 1:
            await self._show_service_menu(message, tail[0], store_key=store_key)
            return
        action, request_id = tail[0], tail[1]
        if action == "rollback":
            keyboard = {
                "inline_keyboard": [
                    [_button(Msg.BTN_BACK, f"inv:service:{request_id}")],
                ]
            }
            await reply_or_edit(message, Msg.SERVICE_ROLLBACK_EMPTY, keyboard)
            return
        if action == "clear":
            await reply_or_edit(message, Msg.SERVICE_CLEAR_STOCK_WARN)
            return

    async def _handle_edit_actions(
        self,
        event: MessageCallback,
        store_key: str,
        data: str,
    ) -> None:
        state = self._edit_state.get(store_key)
        if not state:
            await send_to_user(
                self.bot,
                chat_id=_chat_id(event.message),
                user_id=_sender_id(event) or 0,
                text=Msg.EDIT_NO_ACTIVE,
            )
            return

        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[1]
        message = event.message

        if action == "menu":
            await self._show_edit_menu(message, state)
            return
        if action == "info":
            await self._show_info_fields(message, state)
            return
        if action == "items":
            await self._show_items_list(message, state)
            return
        if action == "done":
            await self._show_final_response(message, state)
            return
        if action == "cancel":
            self._edit_state.pop(store_key, None)
            await reply_or_edit(message, Msg.EDIT_CANCELLED)
            return
        if action == "field" and len(parts) == 3:
            field = parts[2]
            state.mode = "info"
            state.awaiting = field
            await reply_or_edit(
                message,
                Msg.EDIT_ENTER_FIELD.format(field=INFO_FIELDS.get(field, field)),
                self._cancel_keyboard(),
            )
            return
        if action == "item" and len(parts) == 3:
            index = int(parts[2])
            state.mode = "item"
            state.item_index = index
            await self._show_item_fields(message, state)
            return
        if action == "itemfield" and len(parts) == 3:
            field = parts[2]
            state.mode = "itemfield"
            state.awaiting = field
            await reply_or_edit(
                message,
                Msg.EDIT_ENTER_ITEM_FIELD.format(field=ITEM_FIELDS.get(field, field)),
                self._cancel_keyboard(),
            )
            return

    async def _handle_edit_text(self, message: Message, store_key: str, text: str) -> bool:
        state = self._edit_state.get(store_key)
        if not state or not state.awaiting:
            return False
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

    def _cancel_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [_button(Msg.BTN_CANCEL, "edit:cancel", style="danger")],
            ]
        }

    async def _show_edit_menu(self, message: Message, state: EditState) -> None:
        keyboard = {
            "inline_keyboard": [
                [_button(Msg.BTN_EDIT_INFO, "edit:info")],
                [_button(Msg.BTN_EDIT_ITEMS, "edit:items")],
                [
                    _button(Msg.BTN_DONE, "edit:done", style="success"),
                    _button(Msg.BTN_CANCEL, "edit:cancel", style="danger"),
                ],
            ]
        }
        await reply_or_edit(message, Msg.EDIT_WHAT, keyboard)

    async def _show_info_fields(self, message: Message, state: EditState) -> None:
        keyboard = {
            "inline_keyboard": [
                [
                    _button(Msg.INFO_FIELDS["supplier"], "edit:field:supplier"),
                    _button(Msg.INFO_FIELDS["consignee"], "edit:field:consignee"),
                ],
                [_button(Msg.INFO_FIELDS["delivery_address"], "edit:field:delivery_address")],
                [
                    _button(Msg.INFO_FIELDS["invoice_date"], "edit:field:invoice_date"),
                    _button(Msg.INFO_FIELDS["invoice_number"], "edit:field:invoice_number"),
                ],
                [
                    _button(Msg.BTN_BACK, "edit:menu"),
                    _button(Msg.BTN_CANCEL, "edit:cancel", style="danger"),
                ],
            ]
        }
        await reply_or_edit(message, Msg.EDIT_SELECT_FIELD, keyboard)

    async def _show_items_list(self, message: Message, state: EditState) -> None:
        rows: list[list[dict[str, Any]]] = []
        for idx, item in enumerate(state.items[:10], start=1):
            title = item.get("name") or Msg.ITEM_FALLBACK.format(idx=idx)
            rows.append(
                [_button(Msg.BTN_ITEM_ROW.format(index=idx, title=title[:32]), f"edit:item:{idx - 1}")]
            )
        rows.append(
            [
                _button(Msg.BTN_BACK, "edit:menu"),
                _button(Msg.BTN_CANCEL, "edit:cancel", style="danger"),
            ]
        )
        await reply_or_edit(message, Msg.EDIT_SELECT_ITEM, {"inline_keyboard": rows})

    async def _show_item_fields(self, message: Message, state: EditState) -> None:
        keyboard = {
            "inline_keyboard": [
                [_button(Msg.BTN_ITEM_NAME, "edit:itemfield:name")],
                [
                    _button(Msg.BTN_ITEM_QTY, "edit:itemfield:unit_amount"),
                    _button(Msg.BTN_ITEM_PRICE, "edit:itemfield:unit_price"),
                ],
                [
                    _button(Msg.BTN_ITEM_TOTAL, "edit:itemfield:cost_with_tax"),
                    _button(Msg.BTN_ITEM_VAT, "edit:itemfield:tax_amount"),
                ],
                [
                    _button(Msg.BTN_BACK, "edit:items"),
                    _button(Msg.BTN_CANCEL, "edit:cancel", style="danger"),
                ],
            ]
        }
        await reply_or_edit(message, Msg.EDIT_SELECT_ITEM_FIELD, keyboard)

    async def _show_final_response(self, message: Message, state: EditState) -> None:
        text = format_invoice_markdown(
            state.payload,
            overrides=state.overrides,
            items_override=state.items,
        )
        allow_send = not bool(state.payload.get("iiko_uploaded"))
        allow_sync = not bool(state.payload.get("nomenclature_synced"))
        keyboard = build_invoice_actions(
            state.request_id,
            allow_send=allow_send,
            allow_sync=allow_sync,
        )
        await reply_or_edit(message, text, keyboard)

    def _recognition_payload_for_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        view = dict(payload)
        parsed = view.get("parsed")
        if not isinstance(parsed, dict):
            parsed = {}
            view["parsed"] = parsed
        if not parsed.get("items"):
            parsed["items"] = list(view.get("items") or [])
        return view

    async def _show_recognition_card(self, message: Message, payload: dict[str, Any]) -> None:
        view = self._recognition_payload_for_view(payload)
        text = format_invoice_markdown(view)
        sync_note = str(payload.get("nomenclature_sync_note") or "").strip()
        if sync_note:
            text = append_sync_note(text, sync_note)
        allow_send = not bool(payload.get("iiko_uploaded"))
        allow_sync = not bool(payload.get("nomenclature_synced"))
        keyboard = build_invoice_actions(
            str(payload.get("request_id") or ""),
            allow_send=allow_send,
            allow_sync=allow_sync,
        )
        await reply_or_edit(message, text, keyboard)

    async def _show_sync_confirm(self, message: Message, request_id: str, *, store_key: str) -> None:
        await reply_or_edit(message, Msg.SYNC_NOM_CONFIRM, build_sync_confirm_actions(request_id))

    async def _run_sync_nomenclature(self, message: Message, request_id: str, *, store_key: str) -> None:
        await reply_or_edit(message, Msg.SYNC_NOM_PROGRESS)
        try:
            result = await sync_nomenclature_request(self._backend_url, request_id, store_key)
        except Exception:
            logger.exception("Failed to sync nomenclature")
            await reply_or_edit(message, Msg.IIKO_FAILED.format(code_line=""))
            return

        if str(result.get("status") or "").lower() != "ok":
            await reply_or_edit(message, self._format_response(result))
            return

        payload = self._load_request_payload(request_id) or {"request_id": request_id}
        stats = payload.get("nomenclature_sync_stats") or {}
        note = format_sync_note(
            total_rows=int(stats.get("total_rows") or 0),
            matched=int(stats.get("matched") or 0),
            created=int(stats.get("created") or 0),
        )
        payload["nomenclature_sync_note"] = note
        payload["nomenclature_synced"] = True
        self._save_request_payload(request_id, payload)
        await self._show_recognition_card(message, payload)

    def _posting_counts(self, request_id: str) -> tuple[int, int]:
        payload = self._load_request_payload(request_id) or {}
        items = list((payload.get("parsed") or {}).get("items") or payload.get("items") or [])
        return count_posting_rows(items)

    @staticmethod
    def _default_iiko_units() -> list[str]:
        return ["г", "кг", "л", "мл", "шт"]

    async def _show_posting_review(
        self,
        message: Message,
        request_id: str,
        *,
        store_key: str,
        refresh_units: bool = False,
    ) -> None:
        payload = self._load_request_payload(request_id)
        if not payload:
            await send_to_user(
                self.bot,
                chat_id=_chat_id(message),
                user_id=message.sender.user_id if message.sender else 0,
                text=Msg.EDIT_NOT_FOUND_REQUEST,
            )
            return
        units = self._default_iiko_units()
        if refresh_units:
            logger.info("Refresh units for request %s user %s", request_id, store_key)
        view = self._recognition_payload_for_view(payload)
        text = format_posting_review_text(view, units=units)
        _ready, blocked = self._posting_counts(request_id)
        await reply_or_edit(
            message,
            text,
            build_posting_review_actions(request_id, can_confirm=blocked == 0),
        )

    async def _show_back_confirm(self, message: Message, request_id: str) -> None:
        await reply_or_edit(message, Msg.BACK_CONFIRM, build_back_confirm_actions(request_id))

    async def _show_service_menu(self, message: Message, request_id: str, *, store_key: str) -> None:
        payload = self._load_request_payload(request_id) or {}
        allow_rollback = bool(payload.get("iiko_uploaded"))
        await reply_or_edit(
            message,
            Msg.SERVICE_MENU,
            build_service_menu_actions(request_id, allow_rollback=allow_rollback),
        )

    async def _send_to_iiko(self, message: Message, request_id: str, *, store_key: str) -> None:
        code = short_request_code(request_id) or request_id
        code_line = Msg.CODE_LINE.format(code=code) if code else ""

        if request_id in self._iiko_send_inflight:
            await send_to_user(
                self.bot,
                chat_id=_chat_id(message),
                user_id=message.sender.user_id if message.sender else 0,
                text=Msg.IIKO_ALREADY_SENDING.format(code_line=code_line),
            )
            return

        self._iiko_send_inflight.add(request_id)
        try:
            payload = self._load_request_payload(request_id) or {}
            if not payload:
                await reply_or_edit(message, Msg.IIKO_SOURCE_MISSING.format(code_line=code_line))
                return

            await reply_or_edit(message, Msg.IIKO_SENDING.format(code_line=code_line))

            try:
                result = await send_request_to_iiko(self._backend_url, request_id, store_key)
            except Exception:
                logger.exception("Failed to send to iiko")
                await reply_or_edit(message, Msg.IIKO_FAILED.format(code_line=code_line))
                return

            status = str(result.get("status") or "").strip().lower()
            if status == "queued":
                new_request_id = str(result.get("request_id") or "")
                new_code = short_request_code(new_request_id) or new_request_id
                new_code_line = Msg.CODE_LINE.format(code=new_code) if new_code else ""
                await reply_or_edit(message, Msg.IIKO_QUEUED.format(code_line=new_code_line))
                return

            if status == "ok" and result.get("iiko_uploaded"):
                await reply_or_edit(message, Msg.IIKO_OK.format(code_line=code_line))
                return
            if status == "ok" and result.get("iiko_import_ready"):
                fmt = str(result.get("iiko_import_format") or "CSV").upper()
                await reply_or_edit(
                    message,
                    Msg.IIKO_IMPORT_READY.format(fmt=fmt, code_line=code_line),
                )
                return
            if status == "error":
                await reply_or_edit(message, self._format_response(result))
                return

            await reply_or_edit(message, Msg.IIKO_FAILED.format(code_line=code_line))
        finally:
            self._iiko_send_inflight.discard(request_id)

    async def run(self) -> None:
        await self.bot.delete_webhook()
        if self.allowed:
            logger.info("MAX invoice bot polling started (allowed users: %s)", self.allowed)
        else:
            logger.info("MAX invoice bot polling started (access: open — no allowlist)")
        await self.dp.start_polling(self.bot)


def _sender_id_from_message(message: Message) -> int | None:
    if message.sender:
        return message.sender.user_id
    return None


def _max_bot_cmdline_markers() -> tuple[str, ...]:
    return ("experiments.max_invoice_bot", "app.entrypoints.max_bot")


def _ancestor_pids_windows() -> set[int]:
    import subprocess

    current = os.getpid()
    ps = (
        f"$procId = {current}; $seen = @(); "
        "while ($procId -gt 0 -and $seen -notcontains $procId) { "
        "$seen += $procId; "
        "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=$procId\"; "
        "$procId = [int]($p.ParentProcessId); "
        "}; $seen | ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=10,
        ).strip()
    except Exception:
        return {current}
    if not raw or raw == "null":
        return {current}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {current}
    if isinstance(data, int):
        return {data, current}
    return {int(x) for x in data if int(x) > 0} | {current}


def _ensure_single_instance() -> None:
    """Refuse to start if another MAX invoice bot is already polling."""
    if os.name != "nt":
        return
    import subprocess

    current = os.getpid()
    protected = _ancestor_pids_windows()
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=20,
        ).strip()
    except Exception:
        logger.warning("Could not scan for duplicate MAX bot processes")
        return
    if not raw or raw == "null":
        return
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(rows, dict):
        rows = [rows]

    markers = _max_bot_cmdline_markers()
    victims: list[int] = []
    for row in rows:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid == current or pid in protected:
            continue
        cmd = str(row.get("CommandLine") or "")
        if any(marker in cmd for marker in markers):
            victims.append(pid)
    if not victims:
        return
    logger.error(
        "MAX invoice bot already running (PIDs: %s). "
        "Stop other instances first — duplicate pollers send double replies.",
        victims,
    )
    raise SystemExit(1)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    _ensure_single_instance()
    bot = MaxInvoiceBot()
    backoff = 5
    while True:
        try:
            await bot.run()
            break
        except Exception as exc:
            logger.warning(
                "MAX invoice bot polling error (network to MAX?). Will retry in %ss: %s",
                backoff,
                exc,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
