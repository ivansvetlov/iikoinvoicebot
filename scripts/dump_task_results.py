"""Вспомогательный скрипт: выгружает result_json TaskRecord в читаемый JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Чтобы импортировать пакет `app/` при запуске как скрипт.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session

from app.db import _build_engine
from app.models import TaskRecord


def dump(request_id: str, out_path: Path) -> None:
    engine = _build_engine()
    if engine is None:
        out_path.write_text("NO_ENGINE", encoding="utf-8")
        return

    with Session(engine) as session:
        rec = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
        if rec is None:
            out_path.write_text("NOT_FOUND", encoding="utf-8")
            return

        if not rec.result_json:
            payload = {
                "request_id": rec.request_id,
                "status": rec.status,
                "message": rec.message,
                "error": rec.error,
                "iiko_error": rec.iiko_error,
                "iiko_uploaded": rec.iiko_uploaded,
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return

        try:
            obj = json.loads(rec.result_json)
        except Exception:
            obj = {"raw_result_json": rec.result_json}

        obj["_task_record"] = {
            "status": rec.status,
            "message": rec.message,
            "error": rec.error,
            "iiko_error": rec.iiko_error,
            "iiko_uploaded": rec.iiko_uploaded,
        }

        out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    out_dir = Path("tmp")
    out_dir.mkdir(exist_ok=True)

    # Можно передать request_id списком аргументов.
    request_ids = list(sys.argv[1:])
    if not request_ids:
        request_ids = [
            "20260306_001410_276_6106711925",
            "20260307_183952_119_6106711925",
        ]

    for rid in request_ids:
        dump(rid, out_dir / f"task_{rid}.json")

    print("OK")


if __name__ == "__main__":
    main()
