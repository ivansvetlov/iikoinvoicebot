"""Сервисный слой обработки накладных."""

import asyncio
import base64
import json
import logging
import re
from io import BytesIO
from decimal import Decimal
from pathlib import Path
from typing import Any
from datetime import datetime
from uuid import uuid4

import httpx
import pdfplumber
from PIL import Image

from app.config import settings
from app.errors import UserFacingError
from app.iiko.playwright_client import IikoPlaywrightClient
from app.parsers.file_text_extractor import FileTextExtractor
from app.schemas import InvoiceItem, InvoiceParseResult, ProcessResponse
from app.services.user_store import get_iiko_credentials
from app.services.invoice_validator import is_likely_invoice

logger = logging.getLogger(__name__)

REQUESTS_DIR = Path(__file__).resolve().parents[2] / "logs" / "requests"
REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR = REQUESTS_DIR / "users"
USERS_DIR.mkdir(parents=True, exist_ok=True)
LLM_COSTS_LOG = Path(__file__).resolve().parents[2] / "logs" / "llm_costs.csv"
LLM_COSTS_SUMMARY = Path(__file__).resolve().parents[2] / "logs" / "llm_costs_summary.json"
MAX_TEXT_HINT_CHARS = 12000
PDF_IMAGE_RESOLUTION = 200
PDF_SPLIT_HEIGHT_THRESHOLD = 1600

# LLM safety guards
LLM_MAX_OUTPUT_TOKENS = 1000
LLM_MAX_ITEMS = 200
LLM_GARBAGE_REPEAT_THRESHOLD = 8
LLM_GARBAGE_ZERO_ROW_THRESHOLD = 8

USD_RUB_RATE_CACHE: dict[str, Any] = {"rate": None, "ts": None}


class InvoicePipelineService:
    """Оркестрация извлечения текста, парсинга и отправки в iiko."""

    def __init__(self) -> None:
        """Инициализирует клиент iiko для последующей загрузки."""
        self._iiko_client = IikoPlaywrightClient()
        self._pricing = {
            "gpt-4o-mini": {"input": 0.30, "output": 1.20},
            "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        }

    def _build_function_schema(self) -> dict[str, Any]:
        return {
            "name": "parse_invoice",
            "description": "Extract invoice metadata and line items from a document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_type": {"type": "string"},
                    "has_invoice_keyword": {"type": "boolean"},
                    "invoice_number": {"type": "string"},
                    "invoice_date": {"type": "string"},
                    "vendor_name": {"type": "string"},
                    "total_amount": {"type": "number"},
                    "items": {
                        "type": "array",
                        "maxItems": LLM_MAX_ITEMS,
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "line_total": {"type": "number"},
                            },
                            "required": ["description", "quantity", "unit_price", "line_total"],
                        },
                    },
                },
                "required": ["invoice_number", "invoice_date", "vendor_name", "total_amount", "items"],
            },
        }

    def _build_input(
        self, prompt: str, source_type: str, filename: str, content: bytes, extracted_text: str
    ) -> list[dict[str, Any]]:
        if source_type == "image":
            ext = Path(filename).suffix.lower().lstrip(".")
            mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
            image_url = f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
            return [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ]

        # For text/docx, send plain text to reduce cost.
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_text", "text": extracted_text},
                ],
            }
        ]

    def _build_pdf_content(self, prompt: str, extracted_text: str, file_id: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        if extracted_text:
            clipped = extracted_text[:MAX_TEXT_HINT_CHARS]
            content.append(
                {
                    "type": "input_text",
                    "text": "Extracted text (may be incomplete):\n" + clipped,
                }
            )
        content.append({"type": "input_file", "file_id": file_id})
        return [{"role": "user", "content": content}]

    def _estimate_rows(self, raw_text: str) -> int:
        skip_tokens = ("итого", "всего", "ндс", "сумма", "summary", "total")
        header_tokens = ("наименование", "цена", "кол", "кол-во", "ед", "qty", "price", "amount")
        rows = 0
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            lowered = line.lower()
            if any(token in lowered for token in skip_tokens):
                continue
            if any(token in lowered for token in header_tokens):
                continue
            if not re.search(r"[A-Za-zА-Яа-я]", line):
                continue
            numbers = re.findall(r"\d+(?:[.,]\d+)?", line)
            if len(numbers) >= 2:
                rows += 1
        return rows

    def _find_function_call_item(self, data: dict[str, Any]) -> dict[str, Any] | None:
        outputs = data.get("output", [])
        for item in outputs:
            if item.get("type") == "function_call" and item.get("name") == "parse_invoice":
                return item
        return None

    def _parse_function_call(self, data: dict[str, Any]) -> dict[str, Any] | None:
        item = self._find_function_call_item(data)
        if not item:
            return None
        args = item.get("arguments")
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return None
        if isinstance(args, dict):
            return args
        return None

    async def _call_llm(
        self, prompt: str, source_type: str, filename: str, content: bytes, extracted_text: str
    ) -> dict[str, Any]:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        file_id: str | None = None
        if source_type == "pdf":
            file_id = await self._upload_pdf(filename, content)

        if source_type == "pdf" and file_id:
            input_payload = self._build_pdf_content(prompt, extracted_text, file_id)
        else:
            input_payload = self._build_input(prompt, source_type, filename, content, extracted_text)

        payload = {
            "model": settings.openai_model,
            "input": input_payload,
            "tools": [{"type": "function", **self._build_function_schema()}],
            "tool_choice": {"type": "function", "name": "parse_invoice"},
            "temperature": 0,
            "max_output_tokens": LLM_MAX_OUTPUT_TOKENS,
        }

        headers = {
            "authorization": f"Bearer {settings.openai_api_key}",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            if response.status_code >= 400:
                logger.error(
                    "OpenAI error: %s %s", response.status_code, response.text, extra={"request_id": "llm"}
                )
            response.raise_for_status()
            data = response.json()

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        if usage:
            logger.info(
                "LLM usage: %s",
                usage,
                extra={"request_id": "llm"},
            )
            cost = self._estimate_cost(usage)
            if cost:
                logger.info("LLM cost estimate: %s", cost, extra={"request_id": "llm"})
                data["_cost"] = cost
            data["_usage"] = usage

        # Разбор function_call: если модель вернула битый/обрезанный JSON или не вернула tool-call,
        # считаем это ошибкой распознавания (а не "внутренней" ошибкой сервера).
        call_item = self._find_function_call_item(data)
        if not call_item:
            raise UserFacingError(
                "Сервис распознавания вернул неожиданный ответ.",
                hint="Попробуйте отправить фото ещё раз или отправьте PDF.",
                code="llm_bad_response",
            )

        args = call_item.get("arguments")
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except json.JSONDecodeError as exc:
                raise UserFacingError(
                    "Сервис распознавания не смог корректно разобрать документ.",
                    hint="Попробуйте отправить фото целиком (без разрезания) или PDF.",
                    code="llm_bad_response",
                ) from exc
        elif isinstance(args, dict):
            parsed = args
        else:
            raise UserFacingError(
                "Сервис распознавания вернул неожиданный ответ.",
                hint="Попробуйте отправить фото ещё раз или отправьте PDF.",
                code="llm_bad_response",
            )

        if usage:
            parsed["_usage"] = usage
        if data.get("_cost"):
            parsed["_cost"] = data["_cost"]
        return parsed

    def _estimate_cost(self, usage: dict[str, Any]) -> dict[str, Any] | None:
        if not usage:
            return None
        model = settings.openai_model
        pricing = self._pricing.get(model)
        if not pricing:
            return None
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": round(input_cost + output_cost, 6),
        }

    def _build_request_id(self, user_id: str | None) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        user_part = user_id or "anon"
        user_part = "".join(ch if ch.isdigit() else "_" for ch in user_part) or "anon"
        return f"{timestamp}_{user_part}"

    def _append_cost_log(self, user_id: str | None, request_id: str, cost: dict[str, Any]) -> None:
        """Быстро дописывает строку в `logs/llm_costs.csv`.

        Раньше файл перечитывался и перезаписывался целиком (с пересчётом TOTAL/TOTAL_RUB) при каждом запросе,
        что начинало тормозить при росте нагрузки. Для прод-метрик totals лучше считать отдельным батчем/агрегацией.

        Формат строк:
            user_id,request_id,model,input_tokens,output_tokens,input_cost_usd,output_cost_usd,total_cost_usd
        """

        header = "user_id,request_id,model,input_tokens,output_tokens,input_cost_usd,output_cost_usd,total_cost_usd"
        safe_user = user_id or "unknown"

        row = [
            safe_user,
            request_id,
            str(cost.get("model")),
            str(cost.get("input_tokens")),
            str(cost.get("output_tokens")),
            str(cost.get("input_cost_usd")),
            str(cost.get("output_cost_usd")),
            str(cost.get("total_cost_usd")),
        ]

        try:
            # Создаём каталог логов на всякий случай.
            LLM_COSTS_LOG.parent.mkdir(parents=True, exist_ok=True)

            need_header = True
            if LLM_COSTS_LOG.exists():
                try:
                    # Быстрая проверка: файл не пустой и начинается с заголовка.
                    with LLM_COSTS_LOG.open("r", encoding="utf-8", errors="replace") as check:
                        first = check.readline().strip()
                    need_header = not first.startswith("user_id,request_id,")
                except Exception:
                    need_header = True

            with LLM_COSTS_LOG.open("a", encoding="utf-8") as handle:
                if need_header:
                    handle.write(header + "\n")
                handle.write(",".join(row) + "\n")

            self._update_cost_summary(cost)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to append LLM cost log", extra={"request_id": request_id})

    def _update_cost_summary(self, cost: dict[str, Any]) -> None:
        """Обновляет небольшой summary-файл с итогами (без пересчёта всего CSV)."""

        try:
            LLM_COSTS_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
            summary: dict[str, Any] = {}
            if LLM_COSTS_SUMMARY.exists():
                try:
                    summary = json.loads(LLM_COSTS_SUMMARY.read_text(encoding="utf-8"))
                except Exception:
                    summary = {}

            total_usd = float(summary.get("total_usd") or 0.0)
            rows = int(summary.get("rows") or 0)
            added = float(cost.get("total_cost_usd") or 0.0)
            total_usd += added
            rows += 1

            rate = self._get_usd_rub_rate()
            total_rub = round(total_usd * rate, 2) if rate else None

            payload = {
                "total_usd": round(total_usd, 6),
                "total_rub": total_rub,
                "rate": round(rate, 4) if rate else None,
                "rows": rows,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            tmp_path = LLM_COSTS_SUMMARY.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(LLM_COSTS_SUMMARY)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to update LLM cost summary")

    def _get_usd_rub_rate(self) -> float:
        cached = USD_RUB_RATE_CACHE.get("rate")
        ts = USD_RUB_RATE_CACHE.get("ts")
        if cached and ts and (datetime.now() - ts).total_seconds() < 6 * 3600:
            return float(cached)
        try:
            response = httpx.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=15)
            response.raise_for_status()
            text = response.text
            match = re.search(r"<CharCode>USD</CharCode>.*?<Value>([0-9,]+)</Value>", text, re.S)
            if match:
                value = match.group(1).replace(",", ".")
                rate = float(value)
                USD_RUB_RATE_CACHE["rate"] = rate
                USD_RUB_RATE_CACHE["ts"] = datetime.now()
                return rate
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch USD/RUB rate")
        return float(cached) if cached else 0.0

    async def _upload_pdf(self, filename: str, content: bytes) -> str:
        headers = {
            "authorization": f"Bearer {settings.openai_api_key}",
        }
        files = {"file": (filename, content, "application/pdf")}
        data = {"purpose": "user_data"}
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post("https://api.openai.com/v1/files", headers=headers, files=files, data=data)
            if response.status_code >= 400:
                logger.error(
                    "OpenAI file upload error: %s %s",
                    response.status_code,
                    response.text,
                    extra={"request_id": "llm"},
                )
            response.raise_for_status()
            payload = response.json()
        file_id = payload.get("id")
        if not file_id:
            raise RuntimeError("OpenAI file upload did not return file id")
        return file_id

    def _build_items_from_llm(self, data: dict[str, Any]) -> list[InvoiceItem]:
        items: list[InvoiceItem] = []
        for item in data.get("items", []):
            description = item.get("description") or ""
            quantity = item.get("quantity")
            unit_price = item.get("unit_price")
            line_total = item.get("line_total")
            try:
                quantity_dec = Decimal(str(quantity)) if quantity is not None else None
            except Exception:  # noqa: BLE001
                quantity_dec = None
            try:
                unit_price_dec = Decimal(str(unit_price)) if unit_price is not None else None
            except Exception:  # noqa: BLE001
                unit_price_dec = None
            try:
                line_total_dec = Decimal(str(line_total)) if line_total is not None else None
            except Exception:  # noqa: BLE001
                line_total_dec = None

            items.append(
                InvoiceItem(
                    name=description,
                    unit_amount=quantity_dec,
                    supply_quantity=quantity_dec,
                    unit_price=unit_price_dec,
                    cost_without_tax=line_total_dec,
                    cost_with_tax=line_total_dec,
                    total_cost=line_total_dec,
                )
            )
        return items

    def _dedupe_consecutive_items(self, items: list[InvoiceItem]) -> list[InvoiceItem]:
        if not items:
            return items
        deduped: list[InvoiceItem] = []
        last_key: tuple | None = None
        for item in items:
            key = (
                (item.name or "").strip().lower(),
                str(item.unit_amount) if item.unit_amount is not None else "",
                str(item.unit_price) if item.unit_price is not None else "",
                str(item.total_cost) if item.total_cost is not None else "",
            )
            if key == last_key:
                continue
            deduped.append(item)
            last_key = key
        return deduped

    def _detect_garbage_items(self, items: list[InvoiceItem], llm_data: dict[str, Any]) -> list[str]:
        """Возвращает список причин, если ответ похож на мусор/зацикливание."""
        if not items:
            return []

        reasons: list[str] = []

        # 1) Повтор одного и того же описания подряд.
        max_run = 1
        current_run = 1
        prev = (items[0].name or "").strip().lower()
        for item in items[1:]:
            name = (item.name or "").strip().lower()
            if name and name == prev:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
                prev = name
        if max_run >= LLM_GARBAGE_REPEAT_THRESHOLD:
            reasons.append(f"повтор одного и того же описания {max_run} раз подряд")

        # 2) Много строк с нулевыми значениями.
        def is_zero(v) -> bool:
            try:
                return v is None or float(v) == 0.0
            except Exception:
                return False

        zero_rows = 0
        for item in items:
            if is_zero(item.unit_amount) and is_zero(item.unit_price) and is_zero(item.total_cost):
                zero_rows += 1
        if zero_rows >= LLM_GARBAGE_ZERO_ROW_THRESHOLD:
            reasons.append(f"много нулевых строк ({zero_rows})")

        # 3) Стоп-слова, характерные для заголовков/итогов, а не позиций.
        stop_tokens = (
            "масса брутто",
            "итого",
            "всего",
            "ндс",
            "сумма",
            "summary",
            "total",
        )
        stop_hits = sum(1 for item in items if any(tok in (item.name or "").lower() for tok in stop_tokens))
        if stop_hits and stop_hits >= max(3, len(items) // 2):
            reasons.append("похоже на заголовки/итоги вместо товарных позиций")

        # 4) Непоследовательность метаданных.
        if not llm_data.get("has_invoice_keyword") and items:
            reasons.append("has_invoice_keyword=false при наличии позиций")

        return reasons


    async def _extract_items_from_pdf_images(
        self, filename: str, content: bytes, expected_rows: int
    ) -> list[InvoiceItem]:
        prompt = (
            "You are extracting line items from an invoice image. "
            "Return ONLY the parse_invoice function call. "
            "Extract ONLY line items visible in this image. "
            "Do not include items not shown in the image. "
            "If a field is missing for a row, return null for that field."
        )
        items: list[InvoiceItem] = []
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                image = page.to_image(resolution=PDF_IMAGE_RESOLUTION).original
                page_images: list[Image.Image] = [image]
                if image.height >= PDF_SPLIT_HEIGHT_THRESHOLD:
                    mid = image.height // 2
                    top = image.crop((0, 0, image.width, mid))
                    bottom = image.crop((0, mid, image.width, image.height))
                    page_images = [top, bottom]

                for part_index, img in enumerate(page_images, start=1):
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", quality=85)
                    img_bytes = buffer.getvalue()
                    part_name = f"{Path(filename).stem}_p{page_index}_s{part_index}.jpg"
                    data = await self._call_llm(prompt, "image", part_name, img_bytes, "")
                    part_items = self._build_items_from_llm(data)
                    items.extend(part_items)

                    if expected_rows and len(items) >= expected_rows:
                        return self._dedupe_consecutive_items(items)

        return self._dedupe_consecutive_items(items)

    async def process(
        self,
        filename: str,
        content: bytes,
        push_to_iiko: bool = True,
        user_id: str | None = None,
        pdf_mode: str | None = None,
        request_id: str | None = None,
    ) -> ProcessResponse:
        """Обрабатывает файл накладной и формирует итоговый ответ."""
        request_id = request_id or self._build_request_id(user_id)
        logger.info("Processing invoice", extra={"request_id": request_id, "file_name": filename})

        try:
            source_type, raw_text = FileTextExtractor.extract(filename, content)

            prompt = (
                "You are extracting line items from an invoice. "
                "Return ONLY the parse_invoice function call. "
                "Extract ALL line items from the entire document (do not skip any rows). "
                "The table may start in the middle of a page and continue across pages. "
                "Include every row that has a description and any numeric columns "
                "(quantity, unit price, or line total). "
                "Do not stop early. Do not summarize. Do not merge rows. "
                "If a field is missing for a row, return null for that field. "
                "If there are multiple tables, include all line items from all of them. "
                "Also detect document_type: one of 'UPD', 'TORG-12', 'TTN', 'INVOICE', 'OTHER'. "
                "Set has_invoice_keyword=true ONLY if the document visibly contains words like "
                "'накладная', 'УПД', 'ТОРГ-12', or 'товарно-транспортная накладная'. "
                "If it is not an invoice or keywords are not visible, set document_type='OTHER', "
                "has_invoice_keyword=false, and return items as an empty array."
            )

            llm_data = await self._call_llm(prompt, source_type, filename, content, raw_text)

            # Сохраняем стоимость LLM сразу после успешного ответа, независимо от того,
            # распознали мы накладную или вернули пользователю ошибку (not_invoice и пр.).
            if llm_data.get("_cost"):
                self._append_cost_log(user_id, request_id, llm_data["_cost"])

            items = self._build_items_from_llm(llm_data)
            warnings: list[str] = []

            garbage_reasons = self._detect_garbage_items(items, llm_data)
            if garbage_reasons:
                raise UserFacingError(
                    "Не удалось корректно распознать таблицу позиций.",
                    hint=(
                        "Попробуйте отправить фото целиком (одним кадром) или PDF. "
                        "Если фото разрезано на части — попробуйте /split и отправьте части отдельно."
                    ),
                    code="llm_garbage",
                )

            # PDF fallback: если в PDF мало/нет текста, но режим "accurate", пробуем извлечь по картинкам страниц.
            if source_type == "pdf" and getattr(settings, "enable_pdf_image_fallback", True):
                mode = (pdf_mode or "accurate").strip().lower()
                if mode == "accurate":
                    image_items = await self._extract_items_from_pdf_images(filename, content, expected_rows=0)
                    if len(image_items) > len(items):
                        items = image_items

        except UserFacingError as exc:
            logger.info(
                "User-facing parse error: %s",
                exc.code,
                extra={"request_id": request_id, "file_name": filename},
            )
            empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=empty,
                iiko_uploaded=False,
                error_code=exc.code,
                message=exc.to_user_message(),
            )
        except httpx.TimeoutException as exc:
            logger.warning("LLM timeout", extra={"request_id": request_id})
            empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=empty,
                iiko_uploaded=False,
                iiko_error=str(exc),
                error_code="llm_timeout",
                message="Сервис распознавания временно не отвечает. Попробуйте отправить файл чуть позже.",
            )
        except httpx.HTTPError as exc:
            logger.warning("LLM HTTP error", extra={"request_id": request_id})
            empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=empty,
                iiko_uploaded=False,
                iiko_error=str(exc),
                error_code="llm_unavailable",
                message="Сервис распознавания временно недоступен. Попробуйте позже.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to parse invoice", extra={"request_id": request_id})
            empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=empty,
                iiko_uploaded=False,
                iiko_error=str(exc),
                error_code="internal_error",
                message="Не удалось обработать файл на сервере. Попробуйте ещё раз или отправьте файл в другом формате.",
            )

        parsed = InvoiceParseResult(
            source_type=source_type,
            raw_text=raw_text,
            invoice_number=llm_data.get("invoice_number"),
            invoice_date=llm_data.get("invoice_date"),
            vendor_name=llm_data.get("vendor_name"),
            total_amount=Decimal(str(llm_data["total_amount"])) if llm_data.get("total_amount") is not None else None,
            items=items,
            warnings=warnings,
        )

        if not items or not is_likely_invoice(items, raw_text, parsed, source_type, llm_data):
            # Важно: это не "ошибка сервера". Это понятный кейс для пользователя.
            hint = (
                "Проверьте, что на фото/скане видны: название документа (УПД/ТОРГ-12/накладная) и таблица позиций. "
                "Если это скан в PDF — лучше отправить PDF с текстовым слоем или более чёткое фото."
            )
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=parsed,
                iiko_uploaded=False,
                error_code="not_invoice",
                message="Похоже, в файле нет накладной или позиции не читаются. " + hint,
            )

        try:
            payload = {
                "request_id": request_id,
                "filename": filename,
                "source_type": source_type,
                "warnings": warnings,
                "items": [item.model_dump(mode="json") for item in items],
                "raw_text": raw_text,
                "user_id": user_id,
                "document_type": llm_data.get("document_type"),
                "has_invoice_keyword": llm_data.get("has_invoice_keyword"),
                "invoice_number": parsed.invoice_number,
                "invoice_date": parsed.invoice_date,
                "vendor_name": parsed.vendor_name,
                "total_amount": parsed.total_amount,
                "llm_usage": llm_data.get("_usage"),
                "llm_cost": llm_data.get("_cost"),
            }
            (REQUESTS_DIR / f"{request_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            safe_user = user_id or "unknown"
            safe_user = "".join(ch if ch.isdigit() else "_" for ch in safe_user) or "unknown"
            user_path = USERS_DIR / f"{safe_user}.jsonl"
            with user_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str))
                handle.write("\n")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist request payload", extra={"request_id": request_id})

        if not push_to_iiko or not items:
            return ProcessResponse(
                request_id=request_id,
                status="ok",
                parsed=parsed,
                iiko_uploaded=False,
                error_code=None,
                message="Файл обработан. Позиции извлечены.",
            )

        creds = get_iiko_credentials(user_id)
        if not creds:
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=parsed,
                iiko_uploaded=False,
                error_code="iiko_auth_missing",
                message="Нет данных для входа в iiko. Нажмите /start и введите логин/пароль.",
            )

        username, password = creds

        for attempt in range(3):
            try:
                await self._iiko_client.upload_invoice_items(items, username, password)
                return ProcessResponse(
                    request_id=request_id,
                    status="ok",
                    parsed=parsed,
                    iiko_uploaded=True,
                    error_code=None,
                    message="Позиции загружены в iiko.",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "iiko upload failed",
                    extra={"request_id": request_id, "attempt": attempt + 1},
                )
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
                else:
                    return ProcessResponse(
                        request_id=request_id,
                        status="error",
                        parsed=parsed,
                        iiko_uploaded=False,
                        iiko_error=str(exc),
                        error_code="iiko_upload_failed",
                        message="Не удалось загрузить позиции в iiko. Попробуйте позже.",
                    )

    async def process_batch(
        self,
        files: list[tuple[str, bytes]],
        push_to_iiko: bool = True,
        user_id: str | None = None,
        pdf_mode: str | None = None,
        request_id: str | None = None,
    ) -> ProcessResponse:
        """Обрабатывает несколько файлов одной накладной и объединяет позиции."""
        request_id = request_id or self._build_request_id(user_id)
        logger.info("Processing invoice batch", extra={"request_id": request_id, "files": len(files)})

        combined_items: list[InvoiceItem] = []
        warnings: list[str] = []
        meta = {"invoice_number": None, "invoice_date": None, "vendor_name": None, "total_amount": None}

        try:
            for filename, content in files:
                response = await self.process(
                    filename,
                    content,
                    push_to_iiko=False,
                    user_id=user_id,
                    pdf_mode=pdf_mode,
                )
                combined_items.extend(response.parsed.items)
                warnings.extend(response.parsed.warnings)
                if not meta["invoice_number"] and response.parsed.invoice_number:
                    meta["invoice_number"] = response.parsed.invoice_number
                if not meta["invoice_date"] and response.parsed.invoice_date:
                    meta["invoice_date"] = response.parsed.invoice_date
                if not meta["vendor_name"] and response.parsed.vendor_name:
                    meta["vendor_name"] = response.parsed.vendor_name
                if not meta["total_amount"] and response.parsed.total_amount:
                    meta["total_amount"] = response.parsed.total_amount
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to parse invoice batch", extra={"request_id": request_id})
            empty = InvoiceParseResult(source_type="unknown", raw_text="", items=[], warnings=[])
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=empty,
                iiko_uploaded=False,
                iiko_error=str(exc),
                message="Не удалось обработать файлы. Проверьте формат и попробуйте снова.",
            )

        parsed = InvoiceParseResult(
            source_type="unknown",
            raw_text="",
            invoice_number=meta["invoice_number"],
            invoice_date=meta["invoice_date"],
            vendor_name=meta["vendor_name"],
            total_amount=meta["total_amount"],
            items=combined_items,
            warnings=warnings,
        )

        try:
            payload = {
                "request_id": request_id,
                "filename": "batch",
                "source_type": "batch",
                "warnings": warnings,
                "items": [item.model_dump(mode="json") for item in combined_items],
                "raw_text": "",
                "user_id": user_id,
                "invoice_number": parsed.invoice_number,
                "invoice_date": parsed.invoice_date,
                "vendor_name": parsed.vendor_name,
                "total_amount": parsed.total_amount,
            }
            (REQUESTS_DIR / f"{request_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist batch payload", extra={"request_id": request_id})

        if not combined_items or not is_likely_invoice(
            combined_items, "", parsed, "batch", llm_data={"has_invoice_keyword": True}
        ):
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=parsed,
                iiko_uploaded=False,
                error_code="not_invoice",
                message="Похоже, это не накладная. Отправьте корректный документ.",
            )

        if not push_to_iiko:
            return ProcessResponse(
                request_id=request_id,
                status="ok",
                parsed=parsed,
                iiko_uploaded=False,
                error_code=None,
                message="Файлы обработаны. Позиции объединены.",
            )

        creds = get_iiko_credentials(user_id)
        if not creds:
            return ProcessResponse(
                request_id=request_id,
                status="error",
                parsed=parsed,
                iiko_uploaded=False,
                error_code="iiko_auth_missing",
                message="Нет данных для входа в iiko. Нажмите /start и введите логин/пароль.",
            )

        username, password = creds
        for attempt in range(3):
            try:
                await self._iiko_client.upload_invoice_items(combined_items, username, password)
                return ProcessResponse(
                    request_id=request_id,
                    status="ok",
                    parsed=parsed,
                    iiko_uploaded=True,
                    error_code=None,
                    message="Позиции загружены в iiko.",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "iiko batch upload failed",
                    extra={"request_id": request_id, "attempt": attempt + 1},
                )
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
                else:
                    return ProcessResponse(
                        request_id=request_id,
                        status="error",
                        parsed=parsed,
                        iiko_uploaded=False,
                        iiko_error=str(exc),
                        error_code="iiko_upload_failed",
                        message="Не удалось загрузить позиции в iiko. Попробуйте позже.",
                    )
