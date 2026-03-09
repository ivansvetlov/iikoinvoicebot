"""User-facing formatting helpers.

Идея простая:
- Внутренний request_id может быть длинным (нужен для уникальности и логов).
- Пользователю показываем короткий «код заявки», который проще продиктовать/скопировать.

Короткий код делаем детерминированно из request_id:
обычно это `HHMMSS_mmm` (время + миллисекунды).

Важно: это *не* идентификатор безопасности, а просто удобный «чек» для поддержки.
"""

from __future__ import annotations

from typing import Any

from app.config import settings



def short_request_code(request_id: str | None) -> str | None:
    """Делает короткий код для пользователя.

    Пример полного request_id: 20260308_000736_800_6106711925
    Короткий код: 000736_800

    Если формат неожиданный — возвращаем исходный request_id.
    """

    if not request_id:
        return None

    parts = request_id.split("_")

    # Ожидаемый формат: YYYYMMDD_HHMMSS_mmm_<user>
    if len(parts) >= 3 and len(parts[1]) == 6 and len(parts[2]) == 3:
        return f"{parts[1]}_{parts[2]}"

    # На всякий случай: иногда нужные части могут быть в хвосте.
    if len(parts) >= 2 and len(parts[-2]) == 6 and len(parts[-1]) == 3:
        return f"{parts[-2]}_{parts[-1]}"

    return request_id


def format_user_response(payload: dict[str, Any]) -> str:
    """Форматирует сообщение для Telegram.

    Держим формат максимально простым:
    - первая строка: что произошло
    - дальше: важные детали (если есть)
    - последняя строка: короткий код заявки
    """

    status = payload.get("status")
    parsed = payload.get("parsed") or {}
    warnings = parsed.get("warnings") or []
    items = parsed.get("items") or []

    message = payload.get("message")
    error_code = payload.get("error_code")
    request_id = payload.get("request_id")
    code = short_request_code(request_id)

    iiko_uploaded = bool(payload.get("iiko_uploaded"))

    lines: list[str] = []

    if status == "queued":
        lines.append("Принято. Идёт обработка — результат пришлю позже.")
    elif status == "ok":
        lines.append("Готово.")
    elif status == "error":
        lines.append("Не получилось обработать файл.")
    else:
        lines.append(f"Статус: {status}")

    # Основной текст от backend (если есть)
    if message:
        # Не дублируем, если первая строка уже очень похожа на message.
        if message.strip() not in lines:
            lines.append(message.strip())

    # Позиции
    if status == "ok":
        lines.append(f"Позиции: {len(items)}")

    # iiko
    if status == "ok" and iiko_uploaded:
        lines.append("iiko: загружено")

    # Предупреждения
    if warnings:
        lines.append("Предупреждения: " + "; ".join([str(w) for w in warnings[:2]]))

    # Подсказки по error_code (только для ошибок)
    if status == "error" and error_code:
        hints = {
            "unsupported_format": "Поддерживаемые форматы: фото (JPG/PNG), PDF, DOCX.",
            "bad_pdf": "PDF повреждён. Попробуйте пересохранить файл и отправить снова.",
            "bad_docx": "DOCX повреждён. Попробуйте пересохранить файл и отправить снова.",
            "empty_file": "Похоже, файл пустой. Проверьте и отправьте снова.",
            "file_too_large": f"Сожмите файл. Максимум {settings.max_upload_mb} MB.",
            "not_invoice": "Проверьте, что это накладная/УПД/ТОРГ-12 и видно таблицу позиций.",
            "llm_timeout": "Распознавание отвечает медленно. Попробуйте через минуту.",
            "llm_unavailable": "Распознавание временно недоступно. Попробуйте позже.",
            "llm_bad_response": "Распознавание вернуло неполный/некорректный ответ. Попробуйте PDF или фото целиком.",
            "llm_garbage": "Распознавание «зациклилось» (много повторов/нулей). Попробуйте фото целиком или PDF.",
            "iiko_auth_missing": "Нажмите /start и введите логин/пароль iiko.",
            "iiko_upload_failed": "Не удалось загрузить в iiko. Попробуйте позже.",
        }
        hint = hints.get(str(error_code))
        if hint and (not message or hint not in message):
            lines.append(hint)

    # Последняя линия: код
    if code:
        lines.append(f"Код заявки: {code}")

    return "\n".join(lines).strip()
