"""MAX bridge configuration (separate from invoice bot and TG bridge)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DATA = PROJECT_ROOT / "data" / "private" / "grok_max_bridge"
DEFAULT_RULES = PROJECT_ROOT / "experiments" / "grok_max_bridge" / "agents" / "METAPROMPT.md"


class MaxBridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    grok_max_bridge_token: str = Field(default="", alias="GROK_MAX_BRIDGE_TOKEN")
    grok_max_bridge_allowed_user_ids: str = Field(
        default="",
        alias="GROK_MAX_BRIDGE_ALLOWED_USER_IDS",
        description="Comma-separated MAX user IDs",
    )
    grok_cli_path: str = Field(
        default=str(Path.home() / ".grok" / "bin" / "grok.exe"),
        alias="GROK_CLI_PATH",
    )
    grok_bridge_cwd: str = Field(default=str(PROJECT_ROOT), alias="GROK_BRIDGE_CWD")
    grok_bridge_model: str = Field(default="grok-build", alias="GROK_BRIDGE_MODEL")
    grok_bridge_max_turns: int = Field(default=40, alias="GROK_BRIDGE_MAX_TURNS")
    grok_bridge_timeout_sec: int = Field(default=900, alias="GROK_BRIDGE_TIMEOUT_SEC")
    grok_bridge_yolo: bool = Field(default=True, alias="GROK_BRIDGE_YOLO")
    grok_bridge_stream: bool = Field(default=True, alias="GROK_BRIDGE_STREAM")
    grok_bridge_auto_check: bool = Field(
        default=False,
        alias="GROK_BRIDGE_AUTO_CHECK",
    )
    grok_max_bridge_sessions_path: str = Field(
        default=str(BRIDGE_DATA / "sessions.json"),
        alias="GROK_MAX_BRIDGE_SESSIONS_PATH",
    )
    grok_max_bridge_rules_path: str = Field(
        default=str(DEFAULT_RULES),
        alias="GROK_MAX_BRIDGE_RULES_PATH",
    )
    grok_max_bridge_data_dir: str = Field(
        default=str(BRIDGE_DATA),
        alias="GROK_MAX_BRIDGE_DATA_DIR",
    )
    grok_bridge_dashboard_url: str = Field(
        default="http://127.0.0.1:8765/docs/assets/project-dashboard.html",
        alias="GROK_BRIDGE_DASHBOARD_URL",
        description="Local HTTP URL for project dashboard (serve project root on :8765)",
    )

    def allowed_ids(self) -> set[int]:
        raw = (self.grok_max_bridge_allowed_user_ids or "").strip()
        if not raw:
            return set()
        return {int(part.strip()) for part in raw.split(",") if part.strip()}

    def data_dir(self) -> Path:
        return Path(self.grok_max_bridge_data_dir)


from app.bot.max_tokens import validate_max_bot_tokens_from_env  # noqa: E402

validate_max_bot_tokens_from_env()
settings = MaxBridgeSettings()
