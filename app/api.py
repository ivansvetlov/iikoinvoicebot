"""HTTP API для обработки накладных."""

import asyncio
import json
import logging
import sys
from time import perf_counter
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, UploadFile, Request, Response
from aiogram.types import Update

from app.config import settings
from app.observability import configure_logging, track_metric
from app.queue import get_queue
from app.db import init_db
from app.schemas import InvoiceParseResult, ProcessResponse
from app.task_store import create_task
from app.tasks import process_invoice_task
from app.services.pipeline import InvoicePipelineService

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
configure_logging(
    "backend",
    level=settings.log_level,
    max_bytes=settings.log_max_mb * 1024 * 1024,
    backup_count=settings.log_backup_count,
    archive_after_days=settings.log_archive_after_days,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Invoice Ingestion Backend", version="0.1.0")
pipeline = InvoicePipelineService()

WEBHOOK_PATH = "/telegram/webhook"


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        track_metric(
            "http_request",
            component="backend",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        if status_code >= 500:
            logger.error(
                "HTTP 5xx response",
                extra={"event_code": "API_HTTP_5XX", "path": request.url.path, "status_code": status_code},
            )


def _error_response(message: str, exc: Exception | None = None, *, error_code: str = "api_error") -> ProcessResponse:
    request_id = uuid4().hex
    client_side_codes = {"file_too_large", "empty_file", "too_many_files"}
    if exc is not None:
        logger.exception("Unhandled error", extra={"request_id": request_id})
    elif error_code in client_side_codes:
        logger.warning("Client-side validation error: %s", message, extra={"request_id": request_id, "error_code": error_code})
    else:
        logger.error("Error response: %s", message, extra={"request_id": request_id, "error_code": error_code})
    empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
    return ProcessResponse(
        request_id=request_id,
        status="error",
        parsed=empty,
        iiko_uploaded=False,
        iiko_error=str(exc) if exc else None,
        error_code=error_code,
        message=message,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка доступности сервиса."""
    return {"status": "ok"}


@app.on_event("startup")
async def setup_webhook() -> None:
    if not settings.use_webhook or not settings.telegram_bot_token or not settings.webhook_url:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={
                "url": settings.webhook_url.rstrip("/") + WEBHOOK_PATH,
                "secret_token": settings.webhook_secret or None,
            },
        )


@app.on_event("startup")
async def init_database() -> None:
    init_db()
    logger.info("✅ Backend ready (http://127.0.0.1:8000)")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    if settings.webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.webhook_secret:
            return Response(status_code=403)
    body = await request.json()
    update = Update.model_validate(body)
    # reuse manager for handlers
    if not hasattr(app.state, "bot_manager"):
        from app.bot.manager import TelegramBotManager

        app.state.bot_manager = TelegramBotManager(
            settings.telegram_bot_token, str(settings.backend_url)
        )
    manager = app.state.bot_manager
    await manager.dp.feed_update(manager.bot, update)
    return Response(status_code=200)


@app.post("/process", response_model=ProcessResponse)
async def process_invoice(
    file: UploadFile = File(...),
    push_to_iiko: bool = Form(default=True),
    user_id: str | None = Form(default=None),
    pdf_mode: str | None = Form(default=None),
    chat_id: str | None = Form(default=None),
    status_message_id: str | None = Form(default=None),
) -> ProcessResponse:
    """Принимает файл, извлекает позиции и при необходимости отправляет в iiko."""
    logger.info("Received /process request: file=%s, user_id=%s", file.filename, user_id)
    try:
        if file.size and file.size > settings.max_upload_mb * 1024 * 1024:
            return _error_response(
                f"Файл слишком большой. Максимум {settings.max_upload_mb} MB.",
                error_code="file_too_large",
            )
        content = await file.read()
        if not content:
            return _error_response(
                "Пустой файл. Проверьте и отправьте снова.",
                error_code="empty_file",
            )
        logger.info("Received file", extra={"file_name": file.filename})
        request_id = pipeline._build_request_id(user_id)  # noqa: SLF001
        job_dir = Path(__file__).resolve().parent.parent / "data" / "jobs" / request_id
        job_dir.mkdir(parents=True, exist_ok=True)
        file_path = job_dir / (file.filename or "unknown")
        file_path.write_bytes(content)
        payload = {
            "request_id": request_id,
            "filename": file.filename or "unknown",
            "file_path": str(file_path),
            "user_id": user_id,
            "chat_id": int(chat_id) if chat_id else None,
            "status_message_id": int(status_message_id) if status_message_id else None,
            "push_to_iiko": push_to_iiko,
            "pdf_mode": pdf_mode,
        }
        payload_path = job_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        create_task(
            request_id=request_id,
            filename=file.filename or "unknown",
            user_id=user_id,
            chat_id=int(chat_id) if chat_id else None,
            batch=False,
            push_to_iiko=push_to_iiko,
            pdf_mode=pdf_mode,
        )
        get_queue().enqueue(process_invoice_task, str(payload_path))
        empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
        return ProcessResponse(
            request_id=request_id,
            status="queued",
            parsed=empty,
            iiko_uploaded=False,
            message="Файл принят в очередь. Результат пришлем позже.",
        )
    except Exception as exc:  # noqa: BLE001
        return _error_response("Ошибка обработки файла на сервере.", exc)


@app.post("/process-batch", response_model=ProcessResponse)
async def process_batch(
    files: list[UploadFile] = File(...),
    push_to_iiko: bool = Form(default=True),
    user_id: str | None = Form(default=None),
    pdf_mode: str | None = Form(default=None),
    chat_id: str | None = Form(default=None),
    status_message_id: str | None = Form(default=None),
) -> ProcessResponse:
    """Принимает несколько файлов одной накладной, объединяет позиции и отправляет в iiko."""
    try:
        if len(files) > settings.max_files_per_batch:
            return _error_response(
                f"Слишком много файлов в одном запросе. Максимум {settings.max_files_per_batch}.",
                error_code="too_many_files",
            )
        batch: list[tuple[str, bytes]] = []
        for item in files:
            if item.size and item.size > settings.max_upload_mb * 1024 * 1024:
                return _error_response(
                    f"Файл слишком большой. Максимум {settings.max_upload_mb} MB.",
                    error_code="file_too_large",
                )
            content = await item.read()
            if not content:
                return _error_response(
                    "Пустой файл. Проверьте и отправьте снова.",
                    error_code="empty_file",
                )
            batch.append((item.filename or "unknown", content))
        logger.info("Received batch files", extra={"count": len(batch)})
        request_id = pipeline._build_request_id(user_id)  # noqa: SLF001
        job_dir = Path(__file__).resolve().parent.parent / "data" / "jobs" / request_id
        job_dir.mkdir(parents=True, exist_ok=True)
        file_paths: list[str] = []
        for name, content in batch:
            path = job_dir / name
            path.write_bytes(content)
            file_paths.append(str(path))
        payload = {
            "request_id": request_id,
            "files": list(zip([b[0] for b in batch], file_paths)),
            "user_id": user_id,
            "chat_id": int(chat_id) if chat_id else None,
            "status_message_id": int(status_message_id) if status_message_id else None,
            "push_to_iiko": push_to_iiko,
            "pdf_mode": pdf_mode,
            "batch": True,
        }
        payload_path = job_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        create_task(
            request_id=request_id,
            filename=";".join([b[0] for b in batch]),
            user_id=user_id,
            chat_id=int(chat_id) if chat_id else None,
            batch=True,
            push_to_iiko=push_to_iiko,
            pdf_mode=pdf_mode,
        )
        get_queue().enqueue(process_invoice_task, str(payload_path))
        empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
        return ProcessResponse(
            request_id=request_id,
            status="queued",
            parsed=empty,
            iiko_uploaded=False,
            message="Файлы приняты в очередь. Результат пришлем позже.",
        )
    except Exception as exc:  # noqa: BLE001
        return _error_response("Ошибка обработки файлов на сервере.", exc)


@app.post("/iiko-upload-request", response_model=ProcessResponse)
async def iiko_upload_request(
    request_id: str = Form(...),
    user_id: str | None = Form(default=None),
) -> ProcessResponse:
    """Отправляет в iiko ранее распознанную заявку по request_id без повторного OCR/LLM."""
    try:
        return await pipeline.upload_existing_request_to_iiko(
            request_id=request_id,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _error_response("Ошибка отправки в iiko на сервере.", exc)
