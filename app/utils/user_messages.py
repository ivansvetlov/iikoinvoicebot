"""User-facing formatting helpers.

Идея простая:
- Внутренний request_id может быть длинным (нужен для уникальности и логов).
- Пользователю показываем короткий «код заявки», который проще продиктовать/скопировать.

Короткий код делаем детерминированно из request_id:
используем компактный формат из 5 цифр.

Важно: это *не* идентификатор безопасности, а просто удобный «чек» для поддержки.
"""

from __future__ import annotations

import zlib
from typing import Any

from app.bot.messages import Msg
from app.config import settings



def short_request_code(request_id: str | None) -> str | None:
    """Делает короткий код для пользователя.

    Формат: 5 цифр (например, ``48291``), детерминированно от request_id.
    Это удобно диктовать и использовать в поддержке.
    """

    if not request_id:
        return None

    value = zlib.crc32(request_id.encode("utf-8")) % 100000
    return f"{value:05d}"


def format_user_response(payload: dict[str, Any]) -> str:
    """Форматирует сообщение для Telegram.

    Структура:
    - первая строка: краткий статус;
    - блок с деталями (сообщение, позиции, iiko, предупреждения);
    - последняя строка: короткий код заявки.
    """

    status = payload.get("status")
    parsed = payload.get("parsed") or {}
    warnings = parsed.get("warnings") or []
    items = parsed.get("items") or []
    source_type = str(parsed.get("source_type") or payload.get("source_type") or "").lower()
    is_batch = bool(payload.get("batch")) or source_type == "batch"

    message = (payload.get("message") or "").strip()
    error_code = payload.get("error_code")
    request_id = payload.get("request_id")
    code = short_request_code(request_id)

    iiko_uploaded = bool(payload.get("iiko_uploaded"))
    iiko_import_ready = bool(payload.get("iiko_import_ready"))
    iiko_import_format = str(payload.get("iiko_import_format") or "CSV").upper()

    lines: list[str] = []

    # Статус
    if status == "queued":
        if message:
            lines.append(message)
            message = ""
        else:
            lines.append(Msg.RESP_QUEUED_DEFAULT)
    elif status == "ok":
        lines.append(Msg.RESP_OK)
    elif status == "error":
        lines.append(Msg.RESP_ERROR_BATCH if is_batch else Msg.RESP_ERROR)
    else:
        lines.append(Msg.RESP_STATUS.format(status=status))

    # Нормализация текста ошибки для batch: избегаем единственного числа в пользовательском ответе.
    if status == "error" and is_batch and message == Msg.NOT_INVOICE_MESSAGE.strip():
        message = Msg.BATCH_NOT_INVOICE_MESSAGE.strip()

    # Основной текст от backend (если есть)
    if message:
        if message not in lines:
            lines.append("")
            lines.append(message)

    # Детали успешной обработки
    if status == "ok":
        lines.append("")
        lines.append(Msg.RESP_ITEMS_RECOGNIZED.format(count=len(items)))

        if iiko_uploaded:
            lines.append(Msg.RESP_IIKO_UPLOADED)
        elif iiko_import_ready:
            lines.append(Msg.RESP_IIKO_IMPORT_READY.format(fmt=iiko_import_format))

    # Предупреждения
    if warnings:
        lines.append("")
        lines.append(Msg.RESP_WARNINGS.format(warnings="; ".join([str(w) for w in warnings[:2]])))

    # Подсказки по error_code (только для ошибок)
    # Если backend уже прислал текст ошибки, не дублируем подсказку.
    if status == "error" and error_code and not message:
        hint = Msg.RESP_HINTS.get(str(error_code))
        if hint:
            lines.append("")
            lines.append(hint.format(max_upload_mb=settings.max_upload_mb))

    # Последняя линия: код заявки
    if code:
        lines.append("")
        lines.append(Msg.RESP_CODE.format(code=code))

    return "\n".join(lines).strip()


def format_invoice_markdown(
    payload: dict[str, Any],
    overrides: dict[str, str] | None = None,
    items_override: list[dict[str, Any]] | None = None,
) -> str:
    """Форматирует успешный ответ по накладной в человекочитаемый вид."""

    overrides = overrides or {}
    parsed = payload.get("parsed") or {}
    items = items_override or parsed.get("items") or payload.get("items") or []

    supplier = overrides.get("supplier") or parsed.get("vendor_name") or Msg.INVOICE_UNKNOWN
    consignee = overrides.get("consignee") or Msg.INVOICE_UNKNOWN
    delivery = overrides.get("delivery_address") or Msg.INVOICE_UNKNOWN
    date = overrides.get("invoice_date") or parsed.get("invoice_date") or Msg.INVOICE_UNKNOWN
    number = overrides.get("invoice_number") or parsed.get("invoice_number") or Msg.INVOICE_UNKNOWN

    lines: list[str] = [Msg.INVOICE_TITLE]
    if payload.get("iiko_import_ready"):
        fmt = str(payload.get("iiko_import_format") or "CSV").upper()
        lines.append("")
        lines.append(Msg.INVOICE_IMPORT_READY.format(fmt=fmt))
    lines.extend(
        [
            "",
            Msg.INVOICE_SUPPLIER.format(supplier=supplier),
            Msg.INVOICE_CONSIGNEE.format(consignee=consignee),
            Msg.INVOICE_DELIVERY.format(delivery=delivery),
            Msg.INVOICE_DATE.format(date=date),
            Msg.INVOICE_NUMBER.format(number=number),
            "",
            Msg.INVOICE_ITEMS,
        ]
    )

    total_vat = 0.0
    total_sum = 0.0

    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    for index, item in enumerate(items, start=1):
        name = item.get("name") or Msg.INVOICE_UNKNOWN
        qty = item.get("unit_amount") or Msg.INVOICE_UNKNOWN
        price = item.get("unit_price") or Msg.INVOICE_UNKNOWN
        total = item.get("cost_with_tax") or item.get("total_cost") or Msg.INVOICE_UNKNOWN
        vat = item.get("tax_amount") or Msg.INVOICE_UNKNOWN

        total_sum += _to_float(total)
        total_vat += _to_float(vat)

        lines.append(Msg.INVOICE_ITEM_LINE.format(index=index, name=name))
        lines.append(Msg.INVOICE_ITEM_QTY.format(qty=qty))
        lines.append(Msg.INVOICE_ITEM_PRICE.format(price=price))
        lines.append(Msg.INVOICE_ITEM_TOTAL.format(total=total, vat=vat))
        lines.append("")

    lines.append(Msg.INVOICE_SEPARATOR)
    lines.append(Msg.INVOICE_VAT_SUM.format(vat=round(total_vat, 2)))
    lines.append(Msg.INVOICE_TOTAL_SUM.format(total=round(total_sum, 2)))

    code = short_request_code(payload.get("request_id"))
    if code:
        lines.append("")
        lines.append(Msg.RESP_CODE.format(code=code))

    return "\n".join(lines).strip()
