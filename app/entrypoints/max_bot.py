"""Entrypoint invoice-бота для канала MAX (delegates to experiments)."""

from __future__ import annotations

import asyncio

from app.observability import configure_logging
from app.config import settings


async def main() -> None:
    configure_logging(
        "max_bot",
        level=settings.log_level,
        max_bytes=settings.log_max_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
        archive_after_days=settings.log_archive_after_days,
    )
    from experiments.max_invoice_bot.bot import main as max_main

    await max_main()


if __name__ == "__main__":
    asyncio.run(main())
