"""MAX invoice bot settings (reads shared app config + MAX-specific env)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.bot.max_tokens import validate_max_bot_tokens_from_env
from app.config import settings as app_settings


class MaxInvoiceSettings(BaseSettings):
    _env_path = app_settings._env_path  # noqa: SLF001
    model_config = SettingsConfigDict(env_file=_env_path, env_file_encoding="utf-8-sig", extra="ignore")

    max_invoice_bot_token: str = Field(default="", alias="MAX_INVOICE_BOT_TOKEN")
    max_invoice_bot_allowed_user_ids: str = Field(default="", alias="MAX_INVOICE_BOT_ALLOWED_USER_IDS")

    def allowed_ids(self) -> set[int]:
        raw = (self.max_invoice_bot_allowed_user_ids or "").strip()
        if not raw:
            return set()
        out: set[int] = set()
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out

    @property
    def backend_url(self) -> str:
        return str(app_settings.backend_url).rstrip("/")


validate_max_bot_tokens_from_env()
settings = MaxInvoiceSettings()
