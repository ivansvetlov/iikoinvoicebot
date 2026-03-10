"""Entrypoint Telegram-бота для приема накладных."""

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.bot.manager import TelegramBotManager
from app.config import settings

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"
LOCK_FILE = LOG_DIR / "bot.lock"


def _acquire_lock() -> "open file":
    """Гарантирует единственный экземпляр бота через lock-файл.

    Возвращает открытый файл (держим до завершения процесса).
    Если другой экземпляр уже запущен — завершаем процесс с ошибкой.
    """
    try:
        import msvcrt  # Windows

        fh = open(LOCK_FILE, "w", encoding="utf-8")  # noqa: SIM115
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        fh.write(str(Path(sys.executable).resolve()))
        fh.flush()
        return fh
    except (OSError, PermissionError):
        print(
            "\n❌ Другой экземпляр bot.py уже запущен!\n"
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
                "\n❌ Другой экземпляр bot.py уже запущен!\n"
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
    try:
        await manager.run()
    finally:
        lock.close()


if __name__ == "__main__":
    asyncio.run(main())
