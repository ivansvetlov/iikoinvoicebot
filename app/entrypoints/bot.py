"""Entrypoint Telegram-бота для приема накладных."""

import asyncio

from app.bot.manager import TelegramBotManager
from app.config import settings
from app.observability import configure_logging


async def main() -> None:
    """Запускает Telegram-бота через менеджер."""
    configure_logging(
        "bot",
        level=settings.log_level,
        max_bytes=settings.log_max_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
        archive_after_days=settings.log_archive_after_days,
    )
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    manager = TelegramBotManager(settings.telegram_bot_token, str(settings.backend_url))
    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())
