"""Сервисный слой обработки накладных."""

import asyncio
import base64
import json
import logging
import re
import os
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from datetime import datetime
from uuid import uuid4

import httpx
import pdfplumber
from PIL import Image, ImageFilter, ImageOps

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
IMAGE_CROP_BRIGHTNESS = 220
IMAGE_MIN_DIM = 1400
IMAGE_MAX_DIM = 2600
IMAGE_OCR_MAX_CHARS = 6000
IMAGE_OCR_MIN_CHARS = 30
IMAGE_HEADER_PAD_TOP_PCT = 0.02
IMAGE_HEADER_PAD_SIDE_PCT = 0.02
IMAGE_HEADER_MIN_WIDTH_PCT = 0.45
IMAGE_HEADER_MIN_HEIGHT_PCT = 0.25
IMAGE_MAX_DIM_CROPPED = 4200
IMAGE_LINE_SCAN_SCALE = 0.5
IMAGE_LINE_DARK_THRESHOLD = 180
IMAGE_LINE_ROW_RUN_THRESHOLD = 0.6
IMAGE_LINE_ROW_RUN_WEAK_THRESHOLD = 0.3
IMAGE_LINE_ROW_RUN_CLUSTER_PCT = 0.05
IMAGE_LINE_ROW_DARK_THRESHOLD = 0.08
IMAGE_LINE_ROW_ANCHOR_RUN_MIN = 0.2
IMAGE_LINE_ROW_ANCHOR_DARK_MIN = 0.2
IMAGE_LINE_ROW_ANCHOR_OFFSET_PCT = 0.25
IMAGE_LINE_COL_RUN_THRESHOLD = 0.35
IMAGE_LINE_COL_DARK_THRESHOLD = 0.02
IMAGE_LINE_EDGE_IGNORE_PCT = 0.02

# LLM safety guards
LLM_MAX_OUTPUT_TOKENS = 1000
LLM_MAX_OUTPUT_TOKENS_RETRY = 3200
LLM_MAX_ITEMS = 200
LLM_GARBAGE_REPEAT_THRESHOLD = 8
LLM_GARBAGE_ZERO_ROW_THRESHOLD = 8

USD_RUB_RATE_CACHE: dict[str, Any] = {"rate": None, "ts": None}
HEADER_NUMBER_HINT = (
    "The table header may include column index numbers like 1..15. "
    "These are NOT item values. Ignore them and read values from rows below."
)
TTN_LAYOUT_HINT = (
    "If the document uses Form 1-T (товарно-транспортная накладная) with columns 1..12, "
    "map fields by header captions: quantity from 'Количество' (col ~4), "
    "unit_price from 'Цена' (col ~5), item name from 'Наименование продукции/товара' (col ~6), "
    "mass from 'Масса, т' (col ~10), and amount_with_tax from 'Сумма' (col ~11). "
    "Do not use column index numbers as row values."
)
REPEAT_VALUE_HINT = (
    "Do not copy numeric values from one row to others. "
    "Each row can have different quantity, unit price, and line total. "
    "If values vary across rows, keep the variation."
)
QUANTITY_HINT = (
    "Do not assume quantity is 1 by default. "
    "Use the quantity/amount column (e.g., 'кол-во', 'количество', 'масса') if present. "
    "If a line total equals unit price for many rows, re-check the quantity column."
)
CONSISTENCY_HINT = (
    "Ensure arithmetic consistency: amount_without_tax should be approximately unit_price * quantity "
    "(within rounding). If it doesn't match, re-check which column is quantity and which is price."
)
EXCEL_TEMPLATE_FORM_MARKERS = (
    "типовая межотраслевая форма",
    "унифицированная форма",
    "форма по окуд",
    "форма 1-т",
    "форма n 1-т",
    "торг-12",
    "товарно-транспортная накладная",
    "товарная накладная",
)
EXCEL_TEMPLATE_PLACEHOLDER_MARKERS = (
    "полное наименование организации",
    "(организация",
    "по окпо",
    "договор, заказ-наряд",
    "прописью",
    "вид операции",
)


class InvoicePipelineService:
    """Оркестрация извлечения текста, парсинга и отправки в iiko."""

    _ocr_checked = False
    _ocr_available = False
    _pytesseract = None

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
                    "has_receipt_keyword": {"type": "boolean"},
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
                                "name": {"type": "string"},
                                "quantity": {"type": "number"},
                                "mass": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "amount_without_tax": {"type": "number"},
                                "tax_rate": {"type": "number"},
                                "tax_amount": {"type": "number"},
                                "amount_with_tax": {"type": "number"},
                            },
                            "required": ["name"],
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
            text_hint = (extracted_text or "").strip()
            if len(text_hint) > IMAGE_OCR_MAX_CHARS:
                text_hint = text_hint[:IMAGE_OCR_MAX_CHARS]
            header_line = self._find_header_number_line(text_hint)
            return [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        *(
                            [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "Header indices line (column numbers): "
                                        + header_line
                                        + ". Use for alignment only; do not output as data."
                                    ),
                                }
                            ]
                            if header_line
                            else []
                        ),
                        *(
                            [{"type": "input_text", "text": "OCR text (may be noisy):\n" + text_hint}]
                            if text_hint
                            else []
                        ),
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

    def _auto_crop_document(self, image: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(image)
        sample = gray.copy()
        sample.thumbnail((512, 512), Image.BILINEAR)
        width, height = sample.size

        pixels = sample.load()
        min_x, min_y = width, height
        max_x, max_y = -1, -1
        bright_pixels = 0
        total_pixels = width * height
        threshold = IMAGE_CROP_BRIGHTNESS

        for y in range(height):
            for x in range(width):
                if pixels[x, y] >= threshold:
                    bright_pixels += 1
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if bright_pixels < total_pixels * 0.06 or max_x < 0 or max_y < 0:
            return image

        scale_x = image.width / width
        scale_y = image.height / height
        margin_x = int(image.width * 0.02)
        margin_y = int(image.height * 0.02)

        left = max(int(min_x * scale_x) - margin_x, 0)
        top = max(int(min_y * scale_y) - margin_y, 0)
        right = min(int((max_x + 1) * scale_x) + margin_x, image.width)
        bottom = min(int((max_y + 1) * scale_y) + margin_y, image.height)

        if right - left < image.width * 0.35 or bottom - top < image.height * 0.35:
            return image
        if right - left > image.width * 0.98 and bottom - top > image.height * 0.98:
            return image

        return image.crop((left, top, right, bottom))

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        image = image.convert("RGB")
        image = self._auto_crop_document(image)
        image = ImageOps.autocontrast(image)
        before_crop = image.size
        image = self._crop_to_table_header(image)
        was_cropped = image.size != before_crop

        width, height = image.size
        max_dim = max(width, height)
        min_dim = min(width, height)
        max_dim_limit = IMAGE_MAX_DIM_CROPPED if was_cropped else IMAGE_MAX_DIM
        if min_dim < IMAGE_MIN_DIM and max_dim < max_dim_limit:
            scale = IMAGE_MIN_DIM / min_dim
            new_size = (int(width * scale), int(height * scale))
            if max(new_size) <= max_dim_limit:
                image = image.resize(new_size, Image.LANCZOS)

        image = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=180, threshold=2))
        return image

    def _normalize_header_token(self, token: str) -> str:
        token = token.strip().lower()
        token = re.sub(r"[^\w%]+", "", token)
        return token

    def _is_header_tokens(self, tokens: list[str]) -> bool:
        if not tokens:
            return False
        normalized = [self._normalize_header_token(t) for t in tokens if t]
        normalized = [t for t in normalized if t]
        if not normalized:
            return False

        primary_markers = ("наимен", "товар")
        secondary_markers = ("кол", "колич", "ед", "изм", "цена", "сумм", "стоим", "ндс", "ставк", "руб", "коп")

        has_primary = any(any(t.startswith(m) for m in primary_markers) for t in normalized)
        secondary_hits = sum(1 for t in normalized if any(t.startswith(m) for m in secondary_markers))

        if has_primary and secondary_hits >= 1:
            return True
        if secondary_hits >= 3:
            return True
        return False

    def _crop_to_table_header(self, image: Image.Image) -> Image.Image:
        if not getattr(settings, "enable_image_ocr_hint", True):
            return self._crop_to_table_lines(image)
        pytesseract = self._get_pytesseract()
        if not pytesseract:
            return self._crop_to_table_lines(image)
        try:
            data = pytesseract.image_to_data(
                image,
                lang="rus+eng",
                config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return image

        texts = data.get("text") or []
        if not texts:
            return image

        line_map: dict[tuple[int, int, int], dict[str, Any]] = {}
        for idx, text in enumerate(texts):
            if text is None:
                continue
            token = str(text).strip()
            if not token:
                continue
            try:
                conf = float(data.get("conf", [])[idx])
            except Exception:
                conf = -1
            if conf < 0:
                continue
            key = (
                int(data.get("block_num", [])[idx]),
                int(data.get("par_num", [])[idx]),
                int(data.get("line_num", [])[idx]),
            )
            left = int(data.get("left", [])[idx])
            top = int(data.get("top", [])[idx])
            width = int(data.get("width", [])[idx])
            height = int(data.get("height", [])[idx])
            right = left + width
            bottom = top + height

            entry = line_map.get(key)
            if not entry:
                entry = {
                    "tokens": [],
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                }
                line_map[key] = entry
            entry["tokens"].append(token)
            entry["left"] = min(entry["left"], left)
            entry["top"] = min(entry["top"], top)
            entry["right"] = max(entry["right"], right)
            entry["bottom"] = max(entry["bottom"], bottom)

        candidates = [entry for entry in line_map.values() if self._is_header_tokens(entry["tokens"])]
        if not candidates:
            return self._crop_to_table_lines(image)

        candidates.sort(key=lambda entry: entry["top"])
        header = candidates[0]

        pad_top = int(image.height * IMAGE_HEADER_PAD_TOP_PCT)
        pad_side = int(image.width * IMAGE_HEADER_PAD_SIDE_PCT)

        left = max(header["left"] - pad_side, 0)
        right = min(header["right"] + pad_side, image.width)
        top = max(header["top"] - pad_top, 0)
        bottom = image.height

        if right - left < image.width * IMAGE_HEADER_MIN_WIDTH_PCT:
            return image
        if bottom - top < image.height * IMAGE_HEADER_MIN_HEIGHT_PCT:
            return image

        return image.crop((left, top, right, bottom))

    def _crop_to_table_lines(self, image: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(image)
        scale = IMAGE_LINE_SCAN_SCALE
        if scale <= 0 or scale >= 1:
            scale = 0.5
        small = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.BILINEAR)
        width, height = small.size
        if width < 100 or height < 100:
            return image

        pixels = small.load()
        threshold = IMAGE_LINE_DARK_THRESHOLD

        col_runs: list[float] = []
        for x in range(width):
            max_run = 0
            run = 0
            for y in range(height):
                if pixels[x, y] < threshold:
                    run += 1
                    if run > max_run:
                        max_run = run
                else:
                    run = 0
            col_runs.append(max_run / height)

        edge_ignore = int(width * IMAGE_LINE_EDGE_IGNORE_PCT)
        left = None
        right = None
        for x in range(edge_ignore, width - edge_ignore):
            if col_runs[x] >= IMAGE_LINE_COL_RUN_THRESHOLD:
                left = x
                break
        for x in range(width - edge_ignore - 1, edge_ignore - 1, -1):
            if col_runs[x] >= IMAGE_LINE_COL_RUN_THRESHOLD:
                right = x
                break

        def _width_ratio(l: int | None, r: int | None) -> float:
            if l is None or r is None or r <= l:
                return 0.0
            return (r - l) / max(1, width)

        if _width_ratio(left, right) < IMAGE_HEADER_MIN_WIDTH_PCT:
            col_dark: list[float] = []
            for x in range(width):
                dark = 0
                for y in range(height):
                    if pixels[x, y] < threshold:
                        dark += 1
                col_dark.append(dark / height)

            left = None
            right = None
            for x in range(edge_ignore, width - edge_ignore):
                if col_dark[x] >= IMAGE_LINE_COL_DARK_THRESHOLD:
                    left = x
                    break
            for x in range(width - edge_ignore - 1, edge_ignore - 1, -1):
                if col_dark[x] >= IMAGE_LINE_COL_DARK_THRESHOLD:
                    right = x
                    break

        if left is None or right is None or right <= left:
            return image

        region_left = max(left, 0)
        region_right = min(right, width - 1)
        region_width = max(1, region_right - region_left + 1)

        row_dark: list[float] = []
        for y in range(height):
            dark = 0
            for x in range(region_left, region_right + 1):
                if pixels[x, y] < threshold:
                    dark += 1
            row_dark.append(dark / region_width)


        row_runs: list[float] = []
        for y in range(height):
            max_run = 0
            run = 0
            for x in range(region_left, region_right + 1):
                if pixels[x, y] < threshold:
                    run += 1
                    if run > max_run:
                        max_run = run
                else:
                    run = 0
            row_runs.append(max_run / region_width)

        anchor_idx = next(
            (
                i
                for i, ratio in enumerate(row_runs)
                if ratio >= IMAGE_LINE_ROW_ANCHOR_RUN_MIN and row_dark[i] >= IMAGE_LINE_ROW_ANCHOR_DARK_MIN
            ),
            None,
        )

        if anchor_idx is not None:
            offset = int(height * IMAGE_LINE_ROW_ANCHOR_OFFSET_PCT)
            top_row = max(0, anchor_idx - offset)
        else:
            row_hits = [i for i, ratio in enumerate(row_dark) if ratio >= IMAGE_LINE_ROW_DARK_THRESHOLD]
            if not row_hits:
                return image
            cluster_window = max(1, int(height * IMAGE_LINE_ROW_RUN_CLUSTER_PCT))
            top_row = None
            for idx in row_hits:
                if any(other != idx and other <= idx + cluster_window for other in row_hits):
                    top_row = idx
                    break
            if top_row is None:
                top_row = row_hits[0]

        pad_top = int(image.height * IMAGE_HEADER_PAD_TOP_PCT)
        pad_side = int(image.width * IMAGE_HEADER_PAD_SIDE_PCT)

        left_px = max(int(left / scale) - pad_side, 0)
        right_px = min(int((right + 1) / scale) + pad_side, image.width)
        top_px = max(int(top_row / scale) - pad_top, 0)
        bottom_px = image.height

        if right_px - left_px < image.width * IMAGE_HEADER_MIN_WIDTH_PCT:
            return image
        if bottom_px - top_px < image.height * IMAGE_HEADER_MIN_HEIGHT_PCT:
            return image

        return image.crop((left_px, top_px, right_px, bottom_px))

    def _get_pytesseract(self):
        cls = type(self)
        if cls._ocr_checked:
            return cls._pytesseract if cls._ocr_available else None
        try:
            import pytesseract  # type: ignore
            tesseract_cmd = settings.tesseract_cmd or os.environ.get("TESSERACT_CMD", "")
            if not tesseract_cmd:
                default_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                ]
                for candidate in default_paths:
                    if Path(candidate).is_file():
                        tesseract_cmd = candidate
                        break
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            pytesseract.get_tesseract_version()
        except Exception:
            cls._ocr_checked = True
            cls._ocr_available = False
            cls._pytesseract = None
            return None
        cls._ocr_checked = True
        cls._ocr_available = True
        cls._pytesseract = pytesseract
        return pytesseract

    def _extract_ocr_text(self, image: Image.Image) -> str:
        if not getattr(settings, "enable_image_ocr_hint", True):
            return ""
        pytesseract = self._get_pytesseract()
        if not pytesseract:
            return ""
        configs = [
            "--oem 1 --psm 6 -c preserve_interword_spaces=1",
            "--oem 1 --psm 4 -c preserve_interword_spaces=1",
            "--oem 1 --psm 11 -c preserve_interword_spaces=1",
        ]

        def score(text: str) -> int:
            digits = len(re.findall(r"\d", text))
            letters = len(re.findall(r"[A-Za-zА-Яа-я]", text))
            return digits * 2 + letters

        best_text = ""
        best_score = -1
        for config in configs:
            for lang in ("rus+eng", "eng"):
                try:
                    text = pytesseract.image_to_string(image, lang=lang, config=config)
                except Exception:
                    continue
                text = (text or "").strip()
                if not text:
                    continue
                current_score = score(text)
                if current_score > best_score:
                    best_score = current_score
                    best_text = text

        return best_text

    def _prepare_image_payload(self, filename: str, content: bytes) -> tuple[str, bytes, str]:
        raw_image = Image.open(BytesIO(content))
        prepared = self._prepare_image(raw_image.copy())
        ocr_text = self._extract_ocr_text(prepared)
        if len(ocr_text) < IMAGE_OCR_MIN_CHARS:
            raw_text = self._extract_ocr_text(raw_image)
            if len(raw_text) > len(ocr_text):
                ocr_text = raw_text
        buffer = BytesIO()
        prepared.save(buffer, format="JPEG", quality=95)
        new_name = f"{Path(filename).stem}_prep.jpg"
        return new_name, buffer.getvalue(), ocr_text

    def _build_prompt(self, base: str, text_hint: str) -> str:
        return (
            base
            + " Preserve item names exactly as written in the document. "
            + "Do not replace them with more plausible items or categories. "
            + "If text is unclear, keep the best transcription instead of guessing."
        )

    def _normalize_for_matching(self, text: str) -> str:
        normalized = text.lower().replace("ё", "е")
        normalized = re.sub(r"\s*-\s*", "-", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _looks_like_receipt_text(self, text: str) -> bool:
        if not text:
            return False
        normalized = self._normalize_for_matching(text)

        receipt_core_tokens = (
            "кассов",
            "товарн",
            "чек",
            "kacc",
            "yek",
        )
        retail_markers = (
            "касса",
            "смена",
            "сдача",
            "продажа товара",
            "итого к оплате",
            "prodaja tobara",
            "itogo k oplate",
            "smena n",
            "ваша скидка",
            "спасибо за покупку",
            "фн",
            "фд",
            "ккт",
            "рн ккт",
            "len ta",
            "lenta",
            "fehta",
            "kacca",
            "dok n",
        )

        has_core = any(token in normalized for token in receipt_core_tokens)
        marker_hits = sum(1 for token in retail_markers if token in normalized)
        return has_core and marker_hits >= 2

    def _looks_like_excel_reference_template(self, text: str) -> bool:
        if not text:
            return False
        normalized = self._normalize_for_matching(text)
        form_hits = sum(1 for token in EXCEL_TEMPLATE_FORM_MARKERS if token in normalized)
        placeholder_hits = sum(1 for token in EXCEL_TEMPLATE_PLACEHOLDER_MARKERS if token in normalized)
        estimated_rows = self._estimate_rows(text)
        return form_hits >= 2 and placeholder_hits >= 2 and estimated_rows <= 1

    def _find_header_number_line(self, text: str) -> str | None:
        if not text:
            return None
        for line in text.splitlines():
            tokens = re.findall(r"\b\d{1,2}\b", line)
            if len(tokens) < 5:
                continue
            ints = [int(t) for t in tokens]
            if any(value < 1 or value > 20 for value in ints):
                continue
            uniq = sorted(set(ints))
            if len(uniq) < 5:
                continue
            if uniq == list(range(min(uniq), max(uniq) + 1)):
                return line.strip()
        return None

    def _looks_like_column_numbers(self, values: list[Decimal | float | int | None]) -> bool:
        ints: list[int] = []
        for value in values:
            if value is None:
                continue
            try:
                fval = float(value)
            except Exception:
                continue
            if fval.is_integer():
                ival = int(fval)
                if 1 <= ival <= 20:
                    ints.append(ival)
        if len(ints) < 5:
            return False
        uniq = sorted(set(ints))
        if len(uniq) < 5 or max(uniq) > 20:
            return False
        # Sequential header row 1..N or close to it.
        if uniq == list(range(min(uniq), max(uniq) + 1)):
            return True
        return False

    def _detect_header_number_leak(self, items: list[InvoiceItem]) -> bool:
        if not items:
            return False
        prices = [item.unit_price for item in items]
        totals = [item.total_cost for item in items]
        return self._looks_like_column_numbers(prices) or self._looks_like_column_numbers(totals)

    def _dominant_value_ratio(self, values: list[Decimal | float | int | None]) -> tuple[str | None, float]:
        normalized: list[str] = []
        for value in values:
            if value is None:
                continue
            try:
                normalized.append(str(Decimal(str(value))))
            except Exception:
                continue
        if len(normalized) < 3:
            return None, 0.0
        counts: dict[str, int] = {}
        for value in normalized:
            counts[value] = counts.get(value, 0) + 1
        dominant_value, dominant_count = max(counts.items(), key=lambda item: item[1])
        return dominant_value, dominant_count / len(normalized)

    def _detect_repeated_numeric_columns(self, items: list[InvoiceItem]) -> bool:
        if len(items) < 4:
            return False
        price_val, price_ratio = self._dominant_value_ratio([item.unit_price for item in items])
        totals = [
            item.cost_with_tax
            if item.cost_with_tax is not None
            else (item.total_cost if item.total_cost is not None else item.cost_without_tax)
            for item in items
        ]
        total_val, total_ratio = self._dominant_value_ratio(totals)
        qty_val, qty_ratio = self._dominant_value_ratio([item.unit_amount for item in items])
        if price_ratio >= 0.8 and total_ratio >= 0.8 and price_val == total_val:
            return True
        if price_ratio >= 0.85 and qty_ratio >= 0.85:
            return True
        return False

    def _detect_quantity_ignored(self, items: list[InvoiceItem]) -> bool:
        if len(items) < 3:
            return False
        matches = 0
        for item in items:
            qty = item.unit_amount
            price = item.unit_price
            total = item.cost_without_tax if item.cost_without_tax is not None else item.total_cost
            try:
                if qty is not None and float(qty) == 1.0 and price is not None and total is not None:
                    if float(price) == float(total):
                        matches += 1
            except Exception:
                continue
        return matches / len(items) >= 0.7

    def _detect_price_qty_mismatch(self, items: list[InvoiceItem]) -> bool:
        total = 0
        mismatches = 0
        for item in items:
            if item.unit_price is None or item.unit_amount is None or item.cost_without_tax is None:
                continue
            try:
                expected = float(item.unit_price) * float(item.unit_amount)
                actual = float(item.cost_without_tax)
            except Exception:
                continue
            total += 1
            if expected == 0:
                continue
            diff = abs(expected - actual)
            if diff > max(1.0, expected * 0.2):
                mismatches += 1
        return total >= 3 and (mismatches / total) >= 0.6

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

    def _extract_text_from_response(self, data: dict[str, Any]) -> str:
        output = data.get("output", [])
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "output_text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
            if item_type == "message":
                for content in item.get("content", []) or []:
                    if not isinstance(content, dict):
                        continue
                    text = content.get("text") or content.get("output_text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text)
        return "\n".join(chunks).strip()

    def _extract_first_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None

        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```$", "", candidate)
            candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        start = None
        depth = 0
        for idx, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        snippet = text[start : idx + 1]
                        try:
                            parsed = json.loads(snippet)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            continue
        return None

    def _parse_response_text_fallback(self, data: dict[str, Any]) -> dict[str, Any] | None:
        text = self._extract_text_from_response(data)
        if not text:
            return None
        parsed = self._extract_first_json_object(text)
        if not parsed:
            return None
        if "items" not in parsed:
            return None
        return parsed

    def _write_llm_debug_snapshot(
        self,
        *,
        reason: str,
        model: str,
        source_type: str,
        filename: str,
        prompt: str,
        extracted_text: str,
        response_data: dict[str, Any],
    ) -> None:
        try:
            debug_dir = Path(__file__).resolve().parents[2] / "tmp" / "llm_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(filename).name)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            path = debug_dir / f"{stamp}_{reason}_{safe_name}.json"
            payload = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "reason": reason,
                "model": model,
                "source_type": source_type,
                "filename": filename,
                "prompt_head": prompt[:1200],
                "text_hint_head": (extracted_text or "")[:1600],
                "output_text_head": self._extract_text_from_response(response_data)[:2000],
                "response": response_data,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write LLM debug snapshot")

    def _select_model(self, source_type: str, override: str | None = None) -> str:
        if override:
            return override
        if source_type == "image" and settings.openai_model_image:
            return settings.openai_model_image
        return settings.openai_model

    async def _call_llm(
        self,
        prompt: str,
        source_type: str,
        filename: str,
        content: bytes,
        extracted_text: str,
        model_override: str | None = None,
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

        model = self._select_model(source_type, model_override)
        base_payload = {
            "model": model,
            "input": input_payload,
            "tools": [{"type": "function", **self._build_function_schema()}],
            "tool_choice": {"type": "function", "name": "parse_invoice"},
            "temperature": 0,
        }

        headers = {
            "authorization": f"Bearer {settings.openai_api_key}",
            "content-type": "application/json",
        }

        async def _post_once(max_output_tokens: int) -> dict[str, Any]:
            payload = dict(base_payload)
            payload["max_output_tokens"] = max_output_tokens
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
                if response.status_code >= 400:
                    logger.error(
                        "OpenAI error: %s %s",
                        response.status_code,
                        response.text,
                        extra={"request_id": "llm"},
                    )
                response.raise_for_status()
                return response.json()

        data = await _post_once(LLM_MAX_OUTPUT_TOKENS)

        incomplete = isinstance(data, dict) and data.get("status") == "incomplete"
        incomplete_reason = (
            (data.get("incomplete_details") or {}).get("reason")
            if isinstance(data.get("incomplete_details"), dict)
            else None
        )
        if incomplete and incomplete_reason == "max_output_tokens":
            logger.info(
                "Retrying LLM call with larger max_output_tokens due to truncation",
                extra={"request_id": "llm", "model": model},
            )
            data = await _post_once(LLM_MAX_OUTPUT_TOKENS_RETRY)

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        if usage:
            logger.info(
                "LLM usage: %s",
                usage,
                extra={"request_id": "llm"},
            )
            cost = self._estimate_cost(usage, model)
            if cost:
                logger.info("LLM cost estimate: %s", cost, extra={"request_id": "llm"})
                data["_cost"] = cost
            data["_usage"] = usage

        # Разбор function_call: если модель вернула битый/обрезанный JSON или не вернула tool-call,
        # считаем это ошибкой распознавания (а не "внутренней" ошибкой сервера).
        call_item = self._find_function_call_item(data)
        if not call_item:
            parsed_fallback = self._parse_response_text_fallback(data)
            if parsed_fallback is not None:
                if usage:
                    parsed_fallback["_usage"] = usage
                if data.get("_cost"):
                    parsed_fallback["_cost"] = data["_cost"]
                return parsed_fallback
            self._write_llm_debug_snapshot(
                reason="no_function_call",
                model=model,
                source_type=source_type,
                filename=filename,
                prompt=prompt,
                extracted_text=extracted_text,
                response_data=data,
            )
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
                parsed_fallback = self._extract_first_json_object(args)
                if parsed_fallback is not None:
                    parsed = parsed_fallback
                else:
                    self._write_llm_debug_snapshot(
                        reason="bad_function_json",
                        model=model,
                        source_type=source_type,
                        filename=filename,
                        prompt=prompt,
                        extracted_text=extracted_text,
                        response_data=data,
                    )
                    raise UserFacingError(
                        "Сервис распознавания не смог корректно разобрать документ.",
                        hint="Попробуйте отправить фото целиком (без разрезания) или PDF.",
                        code="llm_bad_response",
                    ) from exc
        elif isinstance(args, dict):
            parsed = args
        else:
            self._write_llm_debug_snapshot(
                reason="bad_function_args_type",
                model=model,
                source_type=source_type,
                filename=filename,
                prompt=prompt,
                extracted_text=extracted_text,
                response_data=data,
            )
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

    def _estimate_cost(self, usage: dict[str, Any], model: str) -> dict[str, Any] | None:
        if not usage:
            return None
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

    async def _run_llm_pass(
        self,
        prompt: str,
        source_type: str,
        filename: str,
        content: bytes,
        text_hint: str,
        user_id: str | None,
        request_id: str,
        model_override: str | None = None,
    ) -> tuple[dict[str, Any], list[InvoiceItem], list[str]]:
        async def _attempt(
            attempt_prompt: str,
            attempt_text_hint: str,
            attempt_model: str | None = None,
        ) -> dict[str, Any]:
            return await self._call_llm(
                attempt_prompt,
                source_type,
                filename,
                content,
                attempt_text_hint,
                model_override=attempt_model,
            )

        try:
            llm_data = await _attempt(prompt, text_hint, model_override)
        except UserFacingError as exc:
            if exc.code != "llm_bad_response" or source_type != "image":
                raise

            rescue_prompt = (
                prompt
                + " Always return the parse_invoice function call, even when OCR text is noisy. "
                + "If line items are unreadable, return an empty items array instead of free text."
            )

            # Retry #1: same model, but remove noisy OCR hint from request.
            try:
                llm_data = await _attempt(rescue_prompt, "", model_override)
            except UserFacingError as retry_exc:
                if retry_exc.code != "llm_bad_response":
                    raise

                # Retry #2: optional fallback model for images.
                selected_model = self._select_model(source_type, model_override)
                fallback_model = (settings.openai_model_image_fallback or "").strip()
                if not fallback_model:
                    fallback_model = (settings.openai_model or "").strip()

                if fallback_model and model_override is None and fallback_model != selected_model:
                    llm_data = await _attempt(rescue_prompt, "", fallback_model)
                else:
                    raise

        if llm_data.get("_cost"):
            self._append_cost_log(user_id, request_id, llm_data["_cost"])

        items = self._build_items_from_llm(llm_data)
        garbage_reasons = self._detect_garbage_items(items, llm_data)
        return llm_data, items, garbage_reasons

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
        def _to_decimal(value: Any) -> Decimal | None:
            if value is None:
                return None
            try:
                return Decimal(str(value))
            except Exception:  # noqa: BLE001
                return None

        def _round_money(value: Decimal | None) -> Decimal | None:
            if value is None:
                return None
            try:
                return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:  # noqa: BLE001
                return value

        items: list[InvoiceItem] = []
        for item in data.get("items", []):
            description = item.get("name") or item.get("description") or ""
            quantity_dec = _to_decimal(item.get("quantity"))
            mass_dec = _to_decimal(item.get("mass"))
            unit_price_dec = _to_decimal(item.get("unit_price"))
            amount_without_tax = _to_decimal(item.get("amount_without_tax"))
            tax_rate = _to_decimal(item.get("tax_rate"))
            tax_amount = _to_decimal(item.get("tax_amount"))
            amount_with_tax = _to_decimal(item.get("amount_with_tax"))

            if amount_with_tax is None and amount_without_tax is not None and tax_amount is not None:
                amount_with_tax = amount_without_tax + tax_amount
            if tax_amount is None and amount_with_tax is not None and amount_without_tax is not None:
                tax_amount = amount_with_tax - amount_without_tax
            if tax_rate is None and amount_without_tax is not None and tax_amount is not None:
                try:
                    if amount_without_tax != 0:
                        tax_rate = (tax_amount / amount_without_tax) * Decimal("100")
                except Exception:  # noqa: BLE001
                    tax_rate = None
            if amount_without_tax is None and amount_with_tax is not None and tax_rate is not None:
                try:
                    denom = Decimal("1") + (tax_rate / Decimal("100"))
                    if denom != 0:
                        amount_without_tax = amount_with_tax / denom
                except Exception:  # noqa: BLE001
                    amount_without_tax = None

            amount_without_tax = _round_money(amount_without_tax)
            tax_amount = _round_money(tax_amount)
            amount_with_tax = _round_money(amount_with_tax)

            items.append(
                InvoiceItem(
                    name=description,
                    unit_amount=quantity_dec,
                    supply_quantity=mass_dec,
                    unit_price=unit_price_dec,
                    cost_without_tax=amount_without_tax,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    cost_with_tax=amount_with_tax,
                    total_cost=amount_with_tax,
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

        def is_blank_name(name: str | None) -> bool:
            if not name:
                return True
            stripped = name.strip()
            return stripped in {"-", "—", "–"}

        zero_rows = 0
        blank_rows = 0
        for item in items:
            if is_zero(item.unit_amount) and is_zero(item.unit_price) and is_zero(item.total_cost):
                zero_rows += 1
            if is_blank_name(item.name) and is_zero(item.unit_amount) and is_zero(item.unit_price) and is_zero(
                item.total_cost
            ):
                blank_rows += 1
        if zero_rows >= LLM_GARBAGE_ZERO_ROW_THRESHOLD:
            reasons.append(f"много нулевых строк ({zero_rows})")
        if blank_rows >= max(3, len(items) // 2):
            reasons.append(f"много пустых строк ({blank_rows})")

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
        def has_positive_number(value: Any) -> bool:
            try:
                return Decimal(str(value)) > 0
            except Exception:
                return False

        numeric_rows = sum(
            1
            for item in items
            if item.unit_amount is not None or item.unit_price is not None or item.total_cost is not None
        )
        has_money = any(has_positive_number(item.unit_price) or has_positive_number(item.total_cost) for item in items)
        has_invoice_number = bool(re.search(r"\d", str(llm_data.get("invoice_number") or "")))
        has_total = has_positive_number(llm_data.get("total_amount"))
        doc_type = self._normalize_for_matching(str(llm_data.get("document_type") or ""))
        has_invoice_doc_type = doc_type in {
            "upd",
            "упд",
            "универсальный передаточный документ",
            "torg-12",
            "торг-12",
            "ttn",
            "товарно-транспортная накладная",
            "товарно транспортная накладная",
            "форма 1-т",
            "форма n 1-т",
            "invoice",
            "инвойс",
            "счет-фактура",
            "счет фактура",
        }
        has_receipt_doc_type = doc_type in {"receipt", "retail_receipt", "чек", "кассовый чек", "товарный чек"}
        has_receipt_keyword = bool(llm_data.get("has_receipt_keyword"))
        has_strong_signals = (
            has_invoice_doc_type
            or has_receipt_doc_type
            or has_receipt_keyword
            or ((has_invoice_number or has_total) and has_money and numeric_rows >= 1)
        )

        if llm_data.get("has_invoice_keyword") is False and items and not has_strong_signals:
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
            "Do not invent rows or placeholders. "
            "Do not return rows with empty description. "
            "Preserve item names exactly as written; do not replace them with more plausible items. "
            "If a field is missing for a row, return null for that field. "
            + HEADER_NUMBER_HINT
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
                    img = self._prepare_image(img)
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", quality=90)
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
        source_type = "unknown"
        raw_text = ""

        try:
            source_type, raw_text = FileTextExtractor.extract(filename, content)
            if source_type == "excel" and self._looks_like_excel_reference_template(raw_text):
                parsed = InvoiceParseResult(
                    source_type=source_type,
                    raw_text=raw_text,
                    invoice_number="",
                    invoice_date="",
                    vendor_name="",
                    total_amount=None,
                    items=[],
                    warnings=["excel_reference_template"],
                )
                return ProcessResponse(
                    request_id=request_id,
                    status="ok",
                    parsed=parsed,
                    iiko_uploaded=False,
                    error_code=None,
                    message=(
                        "Распознан Excel-шаблон формы (например, 1-Т/ТОРГ-12) без заполненных товарных строк. "
                        "Шаблон используется как ориентир полей, но для выгрузки нужен заполненный документ."
                    ),
                )

            base_prompt = (
                "You are extracting line items from an invoice. "
                "Return ONLY the parse_invoice function call. "
                "Extract ALL line items from the entire document (do not skip any rows). "
                "The table may start in the middle of a page and continue across pages. "
                "Include every row that has a description and any numeric columns "
                "(quantity, mass, unit price, or totals). "
                "Do not stop early. Do not summarize. Do not merge rows. "
                "Do not invent rows or placeholders. "
                "Do not return rows with empty description. "
                "If a field is missing for a row, return null for that field. "
                "If there are multiple tables, include all line items from all of them. "
                "For each row, return only these fields: name, quantity, mass (if present), unit_price, "
                "amount_without_tax, tax_rate, tax_amount, amount_with_tax. "
                "Map Russian headers: 'кол-во/количество' -> quantity, 'масса/вес' -> mass, "
                "'цена' -> unit_price, 'сумма без НДС/без учета НДС' -> amount_without_tax, "
                "'НДС %/ставка НДС' -> tax_rate, 'сумма НДС/НДС сумма' -> tax_amount, "
                "'сумма с НДС/с НДС/итого' -> amount_with_tax. "
                "If the header shows column numbers 1..15 (TORG-12 layout), align by headers: "
                "price near columns 11, amount_without_tax near 12, tax_rate near 13, tax_amount near 14, "
                "amount_with_tax near 15, quantity (net) near 10. Do not mix these columns. "
                "If there are multiple 'quantity' columns, use the one immediately to the left of the price column "
                "(usually 'Количество (масса нетто)' in TORG-12), not the packaging/count columns on the left. "
                + TTN_LAYOUT_HINT
                + "If quantity and mass are in the same column, use the unit to decide: "
                "weight units (кг, г, л, мл) -> mass; count units (шт, упак, короб, ящик) -> quantity. "
                "If ambiguous or unit is missing, prefer quantity and leave mass null. "
                "If VAT is only provided as a document-level total/rate, do NOT invent per-line VAT amounts; "
                "leave tax_amount null. You may set tax_rate for each line only if it is explicitly visible. "
                "Also detect document_type: one of 'UPD', 'TORG-12', 'TTN', 'INVOICE', 'RECEIPT', 'OTHER'. "
                "Use INVOICE for invoices and VAT invoices (including 'счет-фактура'). "
                "Set has_invoice_keyword=true if the document visibly contains words like "
                "'накладная', 'УПД', 'универсальный передаточный документ', 'счет-фактура', "
                "'ТОРГ-12', 'форма 1-Т', or 'товарно-транспортная накладная'. "
                "Set has_receipt_keyword=true if it visibly contains retail receipt markers like "
                "'кассовый чек', 'товарный чек', 'ККТ', 'ФН', 'ФД', or 'РН ККТ'. "
                "If it is a retail receipt, set document_type='RECEIPT', has_invoice_keyword=false. "
                "If it is not an invoice or keywords are not visible, set document_type='OTHER', "
                "has_invoice_keyword=false, and return items as an empty array."
            )

            original_filename = filename
            original_content = content
            used_prepared = False
            text_hint = raw_text

            if source_type == "image":
                filename, content, ocr_text = self._prepare_image_payload(filename, content)
                used_prepared = True
                if ocr_text:
                    raw_text = ocr_text[:MAX_TEXT_HINT_CHARS]
                    text_hint = raw_text

            prompt = self._build_prompt(base_prompt, text_hint)

            llm_data, items, garbage_reasons = await self._run_llm_pass(
                prompt, source_type, filename, content, text_hint, user_id, request_id
            )
            active_filename = filename
            active_content = content
            active_model = None

            if source_type == "image" and used_prepared and (garbage_reasons or not items):
                raw_data, raw_items, raw_garbage = await self._run_llm_pass(
                    prompt, source_type, original_filename, original_content, text_hint, user_id, request_id
                )
                if raw_items and not raw_garbage:
                    llm_data, items, garbage_reasons = raw_data, raw_items, raw_garbage
                    active_filename = original_filename
                    active_content = original_content

            if items and self._detect_header_number_leak(items):
                header_prompt = prompt + " " + HEADER_NUMBER_HINT
                retry_data, retry_items, retry_garbage = await self._run_llm_pass(
                    header_prompt,
                    source_type,
                    active_filename,
                    active_content,
                    text_hint,
                    user_id,
                    request_id,
                    model_override=active_model,
                )
                if retry_items and not retry_garbage and not self._detect_header_number_leak(retry_items):
                    llm_data, items, garbage_reasons = retry_data, retry_items, retry_garbage

            if items and self._detect_repeated_numeric_columns(items):
                repeat_prompt = prompt + " " + REPEAT_VALUE_HINT
                retry_data, retry_items, retry_garbage = await self._run_llm_pass(
                    repeat_prompt,
                    source_type,
                    active_filename,
                    active_content,
                    text_hint,
                    user_id,
                    request_id,
                    model_override=active_model,
                )
                if retry_items and not retry_garbage and not self._detect_repeated_numeric_columns(retry_items):
                    llm_data, items, garbage_reasons = retry_data, retry_items, retry_garbage

            if items and self._detect_quantity_ignored(items):
                qty_prompt = prompt + " " + QUANTITY_HINT
                retry_data, retry_items, retry_garbage = await self._run_llm_pass(
                    qty_prompt,
                    source_type,
                    active_filename,
                    active_content,
                    text_hint,
                    user_id,
                    request_id,
                    model_override=active_model,
                )
                if retry_items and not retry_garbage and not self._detect_quantity_ignored(retry_items):
                    llm_data, items, garbage_reasons = retry_data, retry_items, retry_garbage

            if items and self._detect_price_qty_mismatch(items):
                consistency_prompt = prompt + " " + CONSISTENCY_HINT
                retry_data, retry_items, retry_garbage = await self._run_llm_pass(
                    consistency_prompt,
                    source_type,
                    active_filename,
                    active_content,
                    text_hint,
                    user_id,
                    request_id,
                    model_override=active_model,
                )
                if retry_items and not retry_garbage and not self._detect_price_qty_mismatch(retry_items):
                    llm_data, items, garbage_reasons = retry_data, retry_items, retry_garbage

            if (
                source_type == "image"
                and settings.openai_model_image_fallback
                and (
                    self._detect_repeated_numeric_columns(items)
                    or self._detect_quantity_ignored(items)
                    or self._detect_price_qty_mismatch(items)
                )
            ):
                fallback_model = settings.openai_model_image_fallback
                fallback_data, fallback_items, fallback_garbage = await self._run_llm_pass(
                    prompt,
                    source_type,
                    active_filename,
                    active_content,
                    text_hint,
                    user_id,
                    request_id,
                    model_override=fallback_model,
                )
                if fallback_items and not fallback_garbage:
                    llm_data, items, garbage_reasons = fallback_data, fallback_items, fallback_garbage

            warnings: list[str] = []
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
                "Проверьте, что на фото/скане видны: название документа "
                "(УПД/ТОРГ-12/1-Т/накладная/счёт-фактура) и таблица позиций. "
                "Также можно отправлять кассовые/товарные чеки с читаемым списком позиций. "
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
                message="Похоже, документ не распознан как накладная/счёт-фактура/чек. Отправьте более чёткий файл.",
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
