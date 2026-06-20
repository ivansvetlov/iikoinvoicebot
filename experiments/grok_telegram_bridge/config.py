"""Bridge configuration (separate from invoice bot)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DATA = PROJECT_ROOT / "data" / "private" / "grok_bridge"
DEFAULT_RULES = PROJECT_ROOT / "experiments" / "grok_telegram_bridge" / "agents" / "METAPROMPT.md"


class BridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    grok_bridge_bot_token: str = Field(default="", alias="GROK_BRIDGE_BOT_TOKEN")
    grok_bridge_allowed_user_ids: str = Field(
        default="",
        alias="GROK_BRIDGE_ALLOWED_USER_IDS",
        description="Comma-separated Telegram user IDs",
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
    grok_bridge_sessions_path: str = Field(
        default=str(BRIDGE_DATA / "sessions.json"),
        alias="GROK_BRIDGE_SESSIONS_PATH",
    )
    grok_bridge_rules_path: str = Field(
        default=str(DEFAULT_RULES),
        alias="GROK_BRIDGE_RULES_PATH",
    )
    grok_bridge_data_dir: str = Field(
        default=str(BRIDGE_DATA),
        alias="GROK_BRIDGE_DATA_DIR",
    )

    def allowed_ids(self) -> set[int]:
        raw = (self.grok_bridge_allowed_user_ids or "").strip()
        if not raw:
            return set()
        return {int(part.strip()) for part in raw.split(",") if part.strip()}

    def data_dir(self) -> Path:
        return Path(self.grok_bridge_data_dir)


settings = BridgeSettings()
