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
    telegram_api_id: int = Field(default=0, alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    max_invoice_bot_token: str = Field(default="", alias="MAX_INVOICE_BOT_TOKEN")
    max_invoice_bot_allowed_user_ids: str = Field(
        default="",
        alias="MAX_INVOICE_BOT_ALLOWED_USER_IDS",
    )
    backend_url: HttpUrl = Field(default="http://127.0.0.1:8000", alias="BACKEND_URL")

    iiko_transport: str = Field(default="import_only", alias="IIKO_TRANSPORT")
    iiko_api_base_url: str = Field(default="", alias="IIKO_API_BASE_URL")
    iiko_api_auth_path: str = Field(default="/resto/api/auth", alias="IIKO_API_AUTH_PATH")
    iiko_api_upload_path: str = Field(default="/resto/api/documents/import/incomingInvoice", alias="IIKO_API_UPLOAD_PATH")
    iiko_api_timeout_sec: int = Field(default=30, alias="IIKO_API_TIMEOUT_SEC")
    iiko_api_verify_tls: bool = Field(default=True, alias="IIKO_API_VERIFY_TLS")
    iiko_username: str = Field(default="", alias="IIKO_USERNAME")
    iiko_password: str = Field(default="", alias="IIKO_PASSWORD")
    iiko_autoresolve_products: bool = Field(default=True, alias="IIKO_AUTORESOLVE_PRODUCTS")
    iiko_autocreate_products: bool = Field(default=False, alias="IIKO_AUTOCREATE_PRODUCTS")
    iiko_autocreate_name_prefix: str = Field(default="", alias="IIKO_AUTOCREATE_NAME_PREFIX")
    iiko_catalog_cache_sec: int = Field(default=300, alias="IIKO_CATALOG_CACHE_SEC")
    iiko_autofill_store: bool = Field(default=True, alias="IIKO_AUTOFILL_STORE")
    iiko_incoming_invoice_status: str = Field(default="NEW", alias="IIKO_INCOMING_INVOICE_STATUS")
    iiko_default_supplier_id: str = Field(default="", alias="IIKO_DEFAULT_SUPPLIER_ID")
    iiko_verify_upload: bool = Field(default=True, alias="IIKO_VERIFY_UPLOAD")
    iiko_verify_stock_balance: bool = Field(default=True, alias="IIKO_VERIFY_STOCK_BALANCE")
    iiko_verify_attempts: int = Field(default=5, alias="IIKO_VERIFY_ATTEMPTS")
    iiko_verify_delay_sec: float = Field(default=1.0, alias="IIKO_VERIFY_DELAY_SEC")
    push_to_iiko: bool = Field(default=True, alias="PUSH_TO_IIKO")
    iiko_import_fallback_enabled: bool = Field(default=True, alias="IIKO_IMPORT_FALLBACK_ENABLED")
    iiko_import_format: str = Field(default="csv", alias="IIKO_IMPORT_FORMAT")
    iiko_import_export_dir: str = Field(default="data/exports/iiko", alias="IIKO_IMPORT_EXPORT_DIR")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_model_image: str = Field(default="", alias="OPENAI_MODEL_IMAGE")
    openai_model_image_fallback: str = Field(default="", alias="OPENAI_MODEL_IMAGE_FALLBACK")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_max_mb: int = Field(default=5, alias="LOG_MAX_MB")
    log_backup_count: int = Field(default=5, alias="LOG_BACKUP_COUNT")
    log_archive_after_days: int = Field(default=7, alias="LOG_ARCHIVE_AFTER_DAYS")

    enable_pdf_image_fallback: bool = Field(default=True, alias="ENABLE_PDF_IMAGE_FALLBACK")
    enable_image_ocr_hint: bool = Field(default=True, alias="ENABLE_IMAGE_OCR_HINT")
    enable_fast_parser_fallback: bool = Field(default=True, alias="ENABLE_FAST_PARSER_FALLBACK")
    fast_parser_min_chars: int = Field(default=120, alias="FAST_PARSER_MIN_CHARS")
    fast_parser_min_items: int = Field(default=2, alias="FAST_PARSER_MIN_ITEMS")
    enable_split_mode: bool = Field(default=True, alias="ENABLE_SPLIT_MODE")
    max_upload_mb: int = Field(default=15, alias="MAX_UPLOAD_MB")
    max_files_per_minute: int = Field(default=10, alias="MAX_FILES_PER_MINUTE")
    max_files_per_batch: int = Field(default=10, alias="MAX_FILES_PER_BATCH")
    status_active_hours: int = Field(default=24, alias="STATUS_ACTIVE_HOURS")
    status_stale_minutes: int = Field(default=20, alias="STATUS_STALE_MINUTES")
    status_auto_reap: bool = Field(default=True, alias="STATUS_AUTO_REAP")
    status_pin_message: bool = Field(default=True, alias="STATUS_PIN_MESSAGE")
    invoice_flow_mode: str = Field(default="legacy", alias="INVOICE_FLOW_MODE")
    invoice_flow_enable_unit_conversion: bool = Field(default=True, alias="INVOICE_FLOW_ENABLE_UNIT_CONVERSION")
    invoice_flow_enable_catalog_match: bool = Field(default=True, alias="INVOICE_FLOW_ENABLE_CATALOG_MATCH")
    invoice_flow_enable_llm_fallback: bool = Field(default=False, alias="INVOICE_FLOW_ENABLE_LLM_FALLBACK")
    invoice_flow_llm_model: str = Field(default="", alias="INVOICE_FLOW_LLM_MODEL")
    invoice_flow_llm_timeout_sec: int = Field(default=20, alias="INVOICE_FLOW_LLM_TIMEOUT_SEC")
    invoice_flow_llm_prompt_fork_path: str = Field(
        default="prompts/invoice_unit_resolution_fork.txt",
        alias="INVOICE_FLOW_LLM_PROMPT_FORK_PATH",
    )
    invoice_flow_owner_rules_path: str = Field(
        default="data/invoice_flow_owner_rules.json",
        alias="INVOICE_FLOW_OWNER_RULES_PATH",
    )

    use_webhook: bool = Field(default=False, alias="USE_WEBHOOK")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    queue_name: str = Field(default="default", alias="QUEUE_NAME")
    worker_ttl_sec: int = Field(default=1800, alias="WORKER_TTL_SEC")
    worker_job_timeout_sec: int = Field(default=600, alias="WORKER_JOB_TIMEOUT_SEC")
    worker_maintenance_interval_sec: int = Field(default=60, alias="WORKER_MAINTENANCE_INTERVAL_SEC")
    worker_job_monitoring_interval_sec: int = Field(default=15, alias="WORKER_JOB_MONITORING_INTERVAL_SEC")

    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")

    # State backend for unified task state (C1 distributed agents).
    # Options: "db" (default, backward compatible), "redis", "hybrid" (future)
    state_backend: str = Field(default="db", alias="STATE_BACKEND")

    # SotaOCR (optional OCR provider — https://sotaocr.com/docs)
    sotaocr_api_key: str = Field(default="", alias="SOTAOCR_API_KEY")
    sotaocr_base_url: str = Field(default="https://sotaocr.com", alias="SOTAOCR_BASE_URL")
    sotaocr_timeout_sec: int = Field(default=600, alias="SOTAOCR_TIMEOUT_SEC")
    sotaocr_poll_interval_sec: float = Field(default=1.0, alias="SOTAOCR_POLL_INTERVAL_SEC")
    sotaocr_model_profile: str = Field(default="", alias="SOTAOCR_MODEL_PROFILE")
    sotaocr_max_retries: int = Field(default=3, alias="SOTAOCR_MAX_RETRIES")
    # Transport: "requests" (stable on Windows) or "auto" (curl first on Windows).
    sotaocr_prefer_curl: str = Field(default="requests", alias="SOTAOCR_PREFER_CURL")
    sotaocr_wg_config: str = Field(
        default="config/wireguard/vpn188958_split_sotaocr.conf",
        alias="SOTAOCR_WG_CONFIG",
    )
    sotaocr_hybrid_enabled: bool = Field(default=True, alias="SOTAOCR_HYBRID_ENABLED")
    sotaocr_hybrid_prompt_path: str = Field(
        default="prompts/sotaocr_hybrid_parse.txt",
        alias="SOTAOCR_HYBRID_PROMPT_PATH",
    )
    sotaocr_hybrid_llm_timeout_sec: int = Field(default=45, alias="SOTAOCR_HYBRID_LLM_TIMEOUT_SEC")
    sotaocr_hybrid_llm_max_attempts: int = Field(default=3, alias="SOTAOCR_HYBRID_LLM_MAX_ATTEMPTS")
    sotaocr_hybrid_openai_probe_timeout_sec: int = Field(
        default=15,
        alias="SOTAOCR_HYBRID_OPENAI_PROBE_TIMEOUT_SEC",
    )
    invoice_venue_context: str = Field(
        default="ресторан или кофейня",
        alias="INVOICE_VENUE_CONTEXT",
    )
    # MAX recognition (user_id max:*): hybrid-only is default; race/vision are opt-in.
    max_recognition_hybrid_only: bool = Field(default=True, alias="MAX_RECOGNITION_HYBRID_ONLY")
    max_recognition_race_enabled: bool = Field(default=False, alias="MAX_RECOGNITION_RACE_ENABLED")
    recognition_race_budget_sec: int = Field(default=90, alias="RECOGNITION_RACE_BUDGET_SEC")
    recognition_vision_budget_sec: int = Field(default=45, alias="RECOGNITION_VISION_BUDGET_SEC")
    recognition_sotaocr_budget_sec: int = Field(default=60, alias="RECOGNITION_SOTA_OCR_BUDGET_SEC")
    max_watch_timeout_sec: int = Field(default=720, alias="MAX_WATCH_TIMEOUT_SEC")
    # Windows dev routing to OpenAI/SotaOCR: wireguard (split-tunnel) or geohide (DNS+Sing-box).
    recognition_route: str = Field(default="wireguard", alias="RECOGNITION_ROUTE")


settings = Settings()
