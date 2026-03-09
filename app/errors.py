"""Единый слой ошибок с user-friendly сообщениями."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserFacingError(Exception):
    """Исключение, которое можно безопасно показать пользователю.

    Attributes:
        message: Текст для пользователя (без технических деталей).
        hint: Доп. подсказка, что сделать дальше.
        code: Машиночитаемый код (для логов/метрик).
    """

    message: str
    hint: str | None = None
    code: str = "user_error"

    def to_user_message(self) -> str:
        if self.hint:
            return f"{self.message}\n{self.hint}"
        return self.message
