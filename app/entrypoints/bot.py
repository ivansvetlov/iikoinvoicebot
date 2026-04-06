"""Entrypoint Telegram-бота для приема накладных."""

import asyncio
import sys
from pathlib import Path

from app.bot.manager import TelegramBotManager
from app.config import settings
from app.observability import LOGS_DIR, configure_logging

LOCK_FILE = LOGS_DIR / "bot.lock"


def _acquire_lock() -> "open file":
    """Гарантирует единственный экземпляр бота через lock-файл.

    Возвращает открытый файл (держим до завершения процесса).
    Если другой экземпляр уже запущен — завершаем процесс с ошибкой.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        import msvcrt  # Windows

        fh = open(LOCK_FILE, "w", encoding="utf-8")  # noqa: SIM115
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        fh.write(str(Path(sys.executable).resolve()))
        fh.flush()
        return fh
    except (OSError, PermissionError):
        print(
            "\n❌ Другой экземпляр бота уже запущен!\n"
            "   Остановите его перед повторным запуском.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError:
        # Unix fallback (fcntl)
        import fcntl  # type: ignore[import-not-found]

        fh = open(LOCK_FILE, "w", encoding="utf-8")  # noqa: SIM115
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(
                "\n❌ Другой экземпляр бота уже запущен!\n"
                "   Остановите его перед повторным запуском.\n",
                file=sys.stderr,
            )
            sys.exit(1)
        fh.write(str(Path(sys.executable).resolve()))
        fh.flush()
        return fh


async def main() -> None:
    """Запускает Telegram-бота через менеджер."""
    lock = _acquire_lock()
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
    try:
        await manager.run()
    finally:
        lock.close()


if __name__ == "__main__":
    asyncio.run(main())
