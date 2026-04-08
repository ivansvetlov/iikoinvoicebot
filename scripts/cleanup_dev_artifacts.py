"""Очистка временных и диагностических файлов в dev-среде.

Скрипт **ничего не делает автоматически**: его нужно запускать вручную,
чтобы удалить старые артефакты разработки.

Что он чистит (по дате):
- `tmp/` — диагностические JSON (diagnose_*/task_*), старше N дней;
- `data/jobs/` — job-директории старше N дней (по mtime каталога);
- `data/pending/`, `data/split/` — старые файлы, если вдруг не убрались ботом;
- `logs/requests/` — старые JSON-результаты (по желанию можно выключить).

По умолчанию порог = 7 дней.

Запуск:
    .venv\\Scripts\\python.exe scripts\\cleanup_dev_artifacts.py

Рекомендуется сначала пробежаться в режиме dry-run (ничего не удаляет),
чтобы посмотреть, что будет трогаться.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CleanupStats:
    removed_files: int = 0
    removed_dirs: int = 0


def _is_older(path: Path, cutoff: datetime) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return False
    return mtime < cutoff


def cleanup_tmp(tmp_dir: Path, cutoff: datetime, dry_run: bool, stats: CleanupStats) -> None:
    if not tmp_dir.exists():
        return
    for path in tmp_dir.iterdir():
        if not _is_older(path, cutoff):
            continue
        if dry_run:
            print(f"[DRY-RUN] tmp: would remove {path}")
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            stats.removed_dirs += 1
        else:
            try:
                path.unlink()
                stats.removed_files += 1
            except OSError:
                pass


def cleanup_jobs(jobs_dir: Path, cutoff: datetime, dry_run: bool, stats: CleanupStats) -> None:
    if not jobs_dir.exists():
        return
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        if not _is_older(job_dir, cutoff):
            continue
        if dry_run:
            print(f"[DRY-RUN] jobs: would remove {job_dir}")
            continue
        shutil.rmtree(job_dir, ignore_errors=True)
        stats.removed_dirs += 1


def cleanup_simple_dir(dir_path: Path, cutoff: datetime, dry_run: bool, stats: CleanupStats, label: str) -> None:
    if not dir_path.exists():
        return
    for path in dir_path.glob("**/*"):
        if not path.is_file():
            continue
        if not _is_older(path, cutoff):
            continue
        if dry_run:
            print(f"[DRY-RUN] {label}: would remove {path}")
            continue
        try:
            path.unlink()
            stats.removed_files += 1
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup dev artifacts (tmp, jobs, pending, split, logs/requests)")
    parser.add_argument("--days", type=int, default=7, help="Сколько дней хранить файлы (по умолчанию 7)")
    parser.add_argument("--no-logs-requests", action="store_true", help="Не трогать logs/requests/")
    parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет удалено, без удаления")
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(days=args.days)
    stats = CleanupStats()

    tmp_dir = PROJECT_ROOT / "tmp"
    jobs_dir = PROJECT_ROOT / "data" / "jobs"
    pending_dir = PROJECT_ROOT / "data" / "pending"
    split_dir = PROJECT_ROOT / "data" / "split"
    requests_dir = PROJECT_ROOT / "logs" / "requests"

    print(f"Cleanup cutoff: {cutoff.isoformat(timespec='seconds')}")

    cleanup_tmp(tmp_dir, cutoff, args.dry_run, stats)
    cleanup_jobs(jobs_dir, cutoff, args.dry_run, stats)
    cleanup_simple_dir(pending_dir, cutoff, args.dry_run, stats, label="pending")
    cleanup_simple_dir(split_dir, cutoff, args.dry_run, stats, label="split")
    if not args.no_logs_requests:
        cleanup_simple_dir(requests_dir, cutoff, args.dry_run, stats, label="logs/requests")

    print("---")
    if args.dry_run:
        print("DRY-RUN complete (ничего не удалено)")
    print(f"Removed files: {stats.removed_files}")
    print(f"Removed dirs: {stats.removed_dirs}")


if __name__ == "__main__":
    main()
