"""Конфигурация приложения и доступ к переменным окружения."""

from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения с загрузкой из .env и переменных окружения."""

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    # NB: используем utf-8-sig, чтобы безопасно читать .env даже если он был сохранён с BOM.
    # Это устраняет класс проблем, когда первый ключ превращается в "\ufeffKEY".
    model_config = SettingsConfigDict(env_file=_env_path, env_file_encoding="utf-8-sig", extra="ignore")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    backend_url: HttpUrl = Field(default="http://127.0.0.1:8000", alias="BACKEND_URL")

    iiko_login_url: str = Field(default="", alias="IIKO_LOGIN_URL")
    iiko_username: str = Field(default="", alias="IIKO_USERNAME")
    iiko_password: str = Field(default="", alias="IIKO_PASSWORD")
    iiko_headless: bool = Field(default=True, alias="IIKO_HEADLESS")
    push_to_iiko: bool = Field(default=True, alias="PUSH_TO_IIKO")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    enable_pdf_image_fallback: bool = Field(default=True, alias="ENABLE_PDF_IMAGE_FALLBACK")
    enable_split_mode: bool = Field(default=True, alias="ENABLE_SPLIT_MODE")
    max_upload_mb: int = Field(default=15, alias="MAX_UPLOAD_MB")
    max_files_per_minute: int = Field(default=10, alias="MAX_FILES_PER_MINUTE")
    max_files_per_batch: int = Field(default=10, alias="MAX_FILES_PER_BATCH")

    use_webhook: bool = Field(default=False, alias="USE_WEBHOOK")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    queue_name: str = Field(default="default", alias="QUEUE_NAME")

    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")

    iiko_selectors_username: str = Field(default="input[name='username']", alias="IIKO_SELECTORS_USERNAME")
    iiko_selectors_password: str = Field(default="input[name='password']", alias="IIKO_SELECTORS_PASSWORD")
    iiko_selectors_submit: str = Field(default="button[type='submit']", alias="IIKO_SELECTORS_SUBMIT")
    iiko_selectors_inventory: str = Field(
        default="div.item-wrapper:has-text('Управление складом')",
        alias="IIKO_SELECTORS_INVENTORY",
    )
    iiko_selectors_new_row: str = Field(default="button[data-action='add-row']", alias="IIKO_SELECTORS_NEW_ROW")
    iiko_selectors_save: str = Field(default="button[data-action='save']", alias="IIKO_SELECTORS_SAVE")


settings = Settings()
