"""Извлечение текста из файлов разных типов.

Принципы:
- PDF/DOCX/TXT извлекаем локально.
- Для изображений (фото/сканы) здесь выполняется только проверка, что файл — валидная картинка.
  OCR/распознавание делается на уровне пайплайна через LLM-Vision.

Этот модуль также нормализует ошибки чтения (битые PDF/DOCX, неподдерживаемые форматы)
в `UserFacingError`, чтобы их можно было безопасно показывать пользователю.
"""

from __future__ import annotations

from io import BytesIO

import pdfplumber
from docx import Document
from PIL import Image

from app.errors import UserFacingError


class FileTextExtractor:
    """Утилиты для определения типа файла и получения текста."""

    @staticmethod
    def detect_source_type(filename: str) -> str:
        """Определяет тип источника по расширению файла."""
        lowered = filename.lower()
        if lowered.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff")):
            return "image"
        if lowered.endswith(".pdf"):
            return "pdf"
        if lowered.endswith(".docx"):
            return "docx"
        if lowered.endswith((".xls", ".xlsx")):
            return "excel"
        if lowered.endswith((".txt", ".csv")):
            return "text"
        return "unknown"

    @staticmethod
    def extract(filename: str, content: bytes) -> tuple[str, str]:
        """Извлекает текст из файла и возвращает (source_type, text).

        Raises:
            UserFacingError: если формат не поддерживается или файл поврежден.
        """
        source_type = FileTextExtractor.detect_source_type(filename)

        if source_type == "unknown":
            raise UserFacingError(
                "Формат файла не поддерживается.",
                hint="Пришлите фото/скан (JPG/PNG), PDF или DOCX.",
                code="unsupported_format",
            )

        if source_type == "image":
            try:
                Image.open(BytesIO(content))
            except Exception as exc:  # noqa: BLE001
                raise UserFacingError(
                    "Не удалось прочитать изображение.",
                    hint="Попробуйте отправить фото ещё раз или в другом формате (JPG/PNG).",
                    code="bad_image",
                ) from exc
            return source_type, ""

        if source_type == "pdf":
            try:
                pages_text: list[str] = []
                with pdfplumber.open(BytesIO(content)) as pdf:
                    for page in pdf.pages:
                        pages_text.append(page.extract_text() or "")
                return source_type, "\n".join(pages_text)
            except Exception as exc:  # noqa: BLE001
                raise UserFacingError(
                    "PDF повреждён или не читается.",
                    hint="Пересохраните PDF (Export/Save As) и отправьте снова.",
                    code="bad_pdf",
                ) from exc

        if source_type == "docx":
            try:
                doc = Document(BytesIO(content))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
                return source_type, text
            except Exception as exc:  # noqa: BLE001
                raise UserFacingError(
                    "DOCX повреждён или не читается.",
                    hint="Пересохраните документ и отправьте снова.",
                    code="bad_docx",
                ) from exc

        if source_type == "text":
            for encoding in ("utf-8", "cp1251", "latin-1"):
                try:
                    return source_type, content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise UserFacingError(
                "Не удалось прочитать текстовый файл.",
                hint="Сохраните файл в UTF-8 и отправьте снова.",
                code="bad_text_encoding",
            )

        if source_type == "excel":
            try:
                import xlrd

                workbook = xlrd.open_workbook(file_contents=content)
                sheets_text: list[str] = []
                for sheet in workbook.sheets():
                    rows: list[str] = []
                    for row_idx in range(sheet.nrows):
                        values = sheet.row_values(row_idx)
                        cells = [
                            str(value).strip()
                            for value in values
                            if value is not None and str(value).strip()
                        ]
                        if cells:
                            rows.append(" ".join(cells))
                    if rows:
                        sheets_text.append("\n".join(rows))
                text = "\n".join(sheets_text)
                if not text.strip():
                    raise UserFacingError(
                        "Файл Excel не содержит читаемых данных.",
                        hint="Проверьте, что таблица не пустая, или отправьте PDF/DOCX.",
                        code="empty_excel",
                    )
                return source_type, text
            except UserFacingError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise UserFacingError(
                    "Не удалось прочитать Excel файл.",
                    hint="Сохраните как PDF или отправьте DOCX.",
                    code="bad_excel",
                ) from exc

        return source_type, ""
