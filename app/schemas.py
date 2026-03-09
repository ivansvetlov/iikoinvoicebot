"""Pydantic-схемы для результатов распознавания и ответов API."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class InvoiceItem(BaseModel):
    """Строка накладной с количественными и ценовыми полями."""

    name: str
    unit_measure: str | None = None
    unit_amount: Decimal | None = None
    unit_price: Decimal | None = None
    supply_quantity: Decimal | None = None
    cost_without_tax: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    cost_with_tax: Decimal | None = None
    total_cost: Decimal | None = None
    currency: str = "RUB"
    extras: dict[str, str] = Field(default_factory=dict)


class InvoiceParseResult(BaseModel):
    """Результат извлечения текста и позиций из файла накладной."""

    source_type: Literal["image", "pdf", "docx", "text", "unknown"]
    raw_text: str = Field(default="")
    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor_name: str | None = None
    total_amount: Decimal | None = None
    items: list[InvoiceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProcessResponse(BaseModel):
    """Ответ API с результатами парсинга и статусом загрузки в iiko."""

    request_id: str
    status: Literal["ok", "error", "queued"]
    parsed: InvoiceParseResult
    iiko_uploaded: bool = False
    iiko_error: str | None = None
    # Машиночитаемый код ошибки (для UX на стороне бота и для метрик).
    error_code: str | None = None
    # Сообщение для пользователя (без технических деталей).
    message: str | None = None
