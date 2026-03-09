r"""Проверка состояния dev-окружения: backend, worker, Redis.

Запуск:
    .venv\Scripts\python.exe scripts\dev_status.py

Скрипт ничего не запускает и не останавливает, только показывает статус.

Важно: скрипт можно запускать из любой директории — он сам добавляет корень
репозитория в `sys.path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from redis import Redis
from rq import Worker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings


def check_backend() -> bool:
    url = "http://127.0.0.1:8000/health"
    try:
        resp = httpx.get(url, timeout=3)
        if resp.status_code == 200:
            print(f"backend: OK ({url})")
            return True
        print(f"backend: ERROR status={resp.status_code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"backend: UNAVAILABLE ({exc.__class__.__name__}: {exc})")
        return False


def check_worker() -> bool:
    try:
        redis = Redis.from_url(settings.redis_url)
    except Exception as exc:  # noqa: BLE001
        print(f"worker: CANNOT CONNECT REDIS ({exc.__class__.__name__}: {exc})")
        return False

    try:
        # RQ: Connection(...) контекстный менеджер deprecated.
        # Используем явный параметр connection.
        workers = Worker.all(connection=redis)
        if not workers:
            print("worker: NO ACTIVE WORKERS")
            return False
        names = ", ".join(w.name for w in workers)
        print(f"worker: OK (workers: {names})")
        return True
    except TypeError:
        # На случай несовпадения API в другой версии rq.
        try:
            workers = Worker.all()
            if not workers:
                print("worker: NO ACTIVE WORKERS")
                return False
            names = ", ".join(w.name for w in workers)
            print(f"worker: OK (workers: {names})")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"worker: ERROR ({exc.__class__.__name__}: {exc})")
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"worker: ERROR ({exc.__class__.__name__}: {exc})")
        return False


def main() -> None:
    print("=== DEV STATUS ===")
    ok_backend = check_backend()
    ok_worker = check_worker()

    if not ok_backend:
        print("\nСовет: запустите backend (uvicorn app.api:app --host 127.0.0.1 --port 8000)")
    if not ok_worker:
        print("Совет: запустите worker (python worker.py)")

    if ok_backend and ok_worker:
        print("\nВсё выглядит запущенным. Если бот не отвечает — проверьте run-конфигурацию bot.py в PyCharm.")


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
