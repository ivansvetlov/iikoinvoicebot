"""Архивирует старые логи в `logs/archive/` (gzip).

Запуск:
    .venv\\Scripts\\python.exe scripts\\archive_logs.py --days 7
"""

from __future__ import annotations

import argparse

from app.observability import archive_logs


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive old logs to logs/archive (gzip).")
    parser.add_argument("--days", type=int, default=7, help="Архивировать файлы старше N дней (по умолчанию 7).")
    args = parser.parse_args()

    result = archive_logs(older_than_days=args.days)
    print(f"Archived: {result['archived']}, skipped: {result['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
