r"""Проверка BOM (UTF-8 with signature) в исходниках.

Запуск:
    .venv\Scripts\python.exe scripts\check_bom.py

Скрипт завершится с кодом 1, если найдёт файлы с BOM.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def has_utf8_bom(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return data.startswith(b"\xef\xbb\xbf")


def main() -> int:
    bad: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.py"):
        # исключаем venv и служебные директории
        rel = path.relative_to(PROJECT_ROOT)
        if any(part in {".venv", "venv", "__pycache__", ".git"} for part in rel.parts):
            continue
        if has_utf8_bom(path):
            bad.append(rel)

    if bad:
        print("Found UTF-8 BOM in files:")
        for p in bad:
            print(" -", p)
        return 1

    print("OK: no UTF-8 BOM found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
