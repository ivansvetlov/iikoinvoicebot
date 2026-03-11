r"""Утилита для удаления UTF-8 BOM (EF BB BF) из текстовых файлов репозитория.

Зачем:
- некоторые редакторы/агенты сохраняют файлы как "UTF-8 with BOM";
- BOM может ломать парсинг .env (первый ключ становится "\ufeffKEY") и другие парсеры.

Запуск (dry-run):
    .venv\Scripts\python.exe scripts\strip_bom.py

Применить изменения:
    .venv\Scripts\python.exe scripts\strip_bom.py --apply

По умолчанию скрипт НЕ модифицирует файлы.
"""

from __future__ import annotations

import argparse
from pathlib import Path

UTF8_BOM = b"\xef\xbb\xbf"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    # runtime dirs
    "logs",
    "data",
    "tmp",
}

# Текстовые расширения. Остальные файлы тоже можно проверить, но лучше не лезть в бинарники.
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".json",
    ".jsonl",
    ".html",
    ".js",
    ".css",
    ".ps1",
    ".sh",
    ".bat",
    ".env",
    ".example",
}

ALWAYS_CHECK_FILENAMES = {
    "README.md",
    "requirements.txt",
    ".editorconfig",
    ".gitignore",
}


def _is_excluded(path: Path) -> bool:
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        return True
    return any(part in EXCLUDE_DIRS for part in rel.parts)


def _looks_texty(path: Path) -> bool:
    if path.name in ALWAYS_CHECK_FILENAMES:
        return True
    ext = path.suffix.lower()
    return ext in TEXT_EXTENSIONS


def strip_bom(path: Path, apply: bool) -> bool:
    """Возвращает True, если файл имел BOM (и был бы исправлен / исправлен)."""
    try:
        data = path.read_bytes()
    except OSError:
        return False

    if not data.startswith(UTF8_BOM):
        return False

    if apply:
        path.write_bytes(data[len(UTF8_BOM) :])
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="перезаписать файлы без BOM")
    args = parser.parse_args()

    touched: list[Path] = []

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path):
            continue
        if not _looks_texty(path):
            continue

        if strip_bom(path, apply=args.apply):
            touched.append(path.relative_to(PROJECT_ROOT))

    if touched:
        print(f"Found BOM in {len(touched)} file(s):")
        for p in sorted(touched):
            print(" -", p.as_posix())
        if not args.apply:
            print("\nRun with --apply to strip BOM.")
            return 1
        print("\nOK: BOM stripped.")
        return 0

    print("OK: no UTF-8 BOM found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
