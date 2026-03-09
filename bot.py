"""Entrypoint Telegram-бота для приема накладных."""

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.bot.manager import TelegramBotManager
from app.config import settings

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"


async def main() -> None:
    """Запускает Telegram-бота через менеджер."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        ],
    )
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    manager = TelegramBotManager(settings.telegram_bot_token, str(settings.backend_url))
    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())
