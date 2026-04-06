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

    message = (payload.get("message") or "").strip()
    error_code = payload.get("error_code")
    request_id = payload.get("request_id")
    code = short_request_code(request_id)

    iiko_uploaded = bool(payload.get("iiko_uploaded"))

    lines: list[str] = []

    # Статус
    if status == "queued":
        if message:
            lines.append(message)
            message = ""
        else:
            lines.append("Принято. Результат пришлю позже.")
    elif status == "ok":
        lines.append("Готово.")
    elif status == "error":
        lines.append("Не получилось обработать файл.")
    else:
        lines.append(f"Статус: {status}")

    # Основной текст от backend (если есть)
    if message:
        if message not in lines:
            lines.append("")
            lines.append(message)

    # Детали успешной обработки
    if status == "ok":
        lines.append("")
        lines.append(f"Распознано позиций: {len(items)}")

        if iiko_uploaded:
            lines.append("iiko: загружено.")

    # Предупреждения
    if warnings:
        lines.append("")
        lines.append("Предупреждения: " + "; ".join([str(w) for w in warnings[:2]]))

    # Подсказки по error_code (только для ошибок)
    # Если backend уже прислал текст ошибки, не дублируем подсказку.
    if status == "error" and error_code and not message:
        hints = {
            "unsupported_format": "Поддерживаемые форматы: фото (JPG/PNG), PDF, DOCX.",
            "bad_pdf": "PDF повреждён. Попробуйте пересохранить файл и отправить снова.",
            "bad_docx": "DOCX повреждён. Попробуйте пересохранить файл и отправить снова.",
            "empty_file": "Похоже, файл пустой. Проверьте и отправьте снова.",
            "file_too_large": f"Сожмите файл. Максимум {settings.max_upload_mb} MB.",
            "not_invoice": (
                "Проверьте, что это накладная, УПД или ТОРГ‑12, "
                "и что видно таблицу с позициями (строки и колонки)."
            ),
            "llm_timeout": "Распознавание отвечает медленно. Попробуйте через минуту.",
            "llm_unavailable": "Распознавание временно недоступно. Попробуйте позже.",
            "llm_bad_response": (
                "Распознавание вернуло неполный или некорректный ответ. "
                "Попробуйте отправить цельный PDF или одно фото накладной."
            ),
            "llm_garbage": (
                "Распознавание «зациклилось» (много повторов или нулей). "
                "Попробуйте одно ровное фото или PDF с цельной таблицей."
            ),
            "iiko_auth_missing": "Нажмите /start и введите логин/пароль iiko.",
            "iiko_upload_failed": "Не удалось загрузить в iiko. Попробуйте позже.",
        }
        hint = hints.get(str(error_code))
        if hint:
            lines.append("")
            lines.append(hint)

    # Последняя линия: код заявки
    if code:
        lines.append("")
        lines.append(f"Код заявки: {code}")

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

    supplier = overrides.get("supplier") or parsed.get("vendor_name") or "—"
    consignee = overrides.get("consignee") or "—"
    delivery = overrides.get("delivery_address") or "—"
    date = overrides.get("invoice_date") or parsed.get("invoice_date") or "—"
    number = overrides.get("invoice_number") or parsed.get("invoice_number") or "—"

    lines: list[str] = [
        "📄 Распознанная накладная",
        "",
        f"📦 Поставщик: {supplier}",
        f"🏢 Грузополучатель: {consignee}",
        f"📍 Адрес доставки: {delivery}",
        f"📅 Дата: {date}",
        f"📋 Номер накладной: {number}",
        "",
        "Товары:",
    ]

    total_vat = 0.0
    total_sum = 0.0

    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    for index, item in enumerate(items, start=1):
        name = item.get("name") or "—"
        qty = item.get("unit_amount") or "—"
        price = item.get("unit_price") or "—"
        total = item.get("cost_with_tax") or item.get("total_cost") or "—"
        vat = item.get("tax_amount") or "—"

        total_sum += _to_float(total)
        total_vat += _to_float(vat)

        lines.append(f"{index}. {name}")
        lines.append(f"- Кол-во: {qty}")
        lines.append(f"- Цена: {price} ₽")
        lines.append(f"- Сумма с НДС: {total} ₽ (НДС: {vat} ₽)")
        lines.append("")

    lines.append("──────────")
    lines.append(f"📊 Сумма НДС: {round(total_vat, 2)} ₽")
    lines.append(f"💰 ИТОГО с НДС: {round(total_sum, 2)} ₽")

    code = short_request_code(payload.get("request_id"))
    if code:
        lines.append("")
        lines.append(f"Код заявки: {code}")

    return "\n".join(lines).strip()
