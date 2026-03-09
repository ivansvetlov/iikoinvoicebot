"""Диагностика обработки по request_id.

Использование:
  python scripts/diagnose_request.py <request_id_or_fragment>

Примеры:
  python scripts/diagnose_request.py 20260308_000736_800_6106711925
  python scripts/diagnose_request.py 000736_800

Скрипт:
- находит request_id по фрагменту (по папкам data/jobs и по БД)
- выводит TaskRecord (status/message/error/error_code)
- выводит payload.json и список файлов
- пишет компактный JSON-отчёт в tmp/diagnose_<request_id>.json

Важно: скрипт не модифицирует данные проекта.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Чтобы импортировать пакет `app/` при запуске как скрипт.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session

from app.db import _build_engine
from app.models import TaskRecord


DATA_JOBS_DIR = PROJECT_ROOT / "data" / "jobs"
LOGS_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / "tmp"
LLM_COSTS_CSV = LOGS_DIR / "llm_costs.csv"


@dataclass(frozen=True)
class Match:
    request_id: str
    source: str


def _sha256(path: Path, limit_bytes: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        if limit_bytes is None:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        else:
            remaining = limit_bytes
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                h.update(chunk)
                remaining -= len(chunk)
    return h.hexdigest()


def _tail_lines(path: Path, n: int = 120) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[-n:]]
    except Exception:
        return []


def _find_by_job_dirs(fragment: str) -> list[Match]:
    if not DATA_JOBS_DIR.exists():
        return []
    matches: list[Match] = []
    for p in DATA_JOBS_DIR.iterdir():
        if p.is_dir() and fragment in p.name:
            matches.append(Match(request_id=p.name, source="data/jobs"))
    return matches


def _find_by_db(fragment: str) -> list[Match]:
    engine = _build_engine()
    if engine is None:
        return []
    with Session(engine) as s:
        rows = (
            s.query(TaskRecord)
            .filter(TaskRecord.request_id.contains(fragment))
            .order_by(TaskRecord.created_at.desc())
            .limit(20)
            .all()
        )
    return [Match(request_id=r.request_id, source="db") for r in rows]


def _load_task_record(request_id: str) -> dict[str, Any] | None:
    engine = _build_engine()
    if engine is None:
        return None
    with Session(engine) as s:
        rec = s.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
        if rec is None:
            return None
        return {
            "request_id": rec.request_id,
            "status": rec.status,
            "message": rec.message,
            "error": rec.error,
            "error_code": getattr(rec, "error_code", None),
            "iiko_uploaded": rec.iiko_uploaded,
            "iiko_error": rec.iiko_error,
            "created_at": str(getattr(rec, "created_at", None)),
            "updated_at": str(getattr(rec, "updated_at", None)),
            "result_json_len": len(rec.result_json or ""),
        }


def _load_payload(request_id: str) -> dict[str, Any] | None:
    payload_path = DATA_JOBS_DIR / request_id / "payload.json"
    if not payload_path.exists():
        return None
    try:
        return json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(payload_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return {"_raw": payload_path.read_text(encoding="utf-8", errors="replace")}


def _list_job_files(request_id: str) -> list[dict[str, Any]]:
    job_dir = DATA_JOBS_DIR / request_id
    if not job_dir.exists():
        return []

    out: list[dict[str, Any]] = []
    for p in sorted(job_dir.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.name == "payload.json":
            continue
        try:
            out.append(
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "sha256": _sha256(p, limit_bytes=5 * 1024 * 1024),
                }
            )
        except Exception as e:
            out.append({"name": p.name, "error": f"hash_failed: {e}"})
    return out


def _load_llm_costs(request_id: str) -> list[dict[str, Any]]:
    if not LLM_COSTS_CSV.exists():
        return []

    rows: list[dict[str, Any]] = []
    with LLM_COSTS_CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("request_id") == request_id:
                rows.append(row)

    return rows


def _resolve_request_id(fragment: str) -> tuple[str | None, list[Match]]:
    # 1) По папкам jobs
    job_matches = _find_by_job_dirs(fragment)
    if len(job_matches) == 1:
        return job_matches[0].request_id, job_matches

    # 2) По БД
    db_matches = _find_by_db(fragment)
    all_matches = {m.request_id: m for m in (job_matches + db_matches)}
    if len(all_matches) == 1:
        return next(iter(all_matches.values())).request_id, list(all_matches.values())

    return None, list(all_matches.values())


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_request.py <request_id_or_fragment>")
        sys.exit(2)

    fragment = sys.argv[1].strip()
    request_id, matches = _resolve_request_id(fragment)

    if request_id is None:
        print(f"Не удалось однозначно определить request_id по фрагменту: {fragment}")
        print("Найденные совпадения (до 20):")
        for m in matches[:20]:
            print(f"- {m.request_id}  (source={m.source})")
        sys.exit(1)

    task = _load_task_record(request_id)
    payload = _load_payload(request_id)
    files = _list_job_files(request_id)
    llm_costs = _load_llm_costs(request_id)

    report = {
        "request_id": request_id,
        "task_record": task,
        "payload": payload,
        "job_files": files,
        "llm_costs": llm_costs,
        "bot_log_tail": _tail_lines(LOGS_DIR / "bot.log", n=80),
        "backend_log_tail": _tail_lines(LOGS_DIR / "backend.log", n=120),
    }

    TMP_DIR.mkdir(exist_ok=True)
    out_path = TMP_DIR / f"diagnose_{request_id}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Короткий человекочитаемый вывод
    print("=" * 80)
    print(f"request_id: {request_id}")

    if task:
        print(f"status: {task.get('status')}")
        if task.get("error_code"):
            print(f"error_code: {task.get('error_code')}")
        if task.get("error"):
            print(f"error: {task.get('error')}")
        print(f"message: {task.get('message')}")
    else:
        print("TaskRecord: NOT_FOUND (или engine отключён)")

    if payload:
        print("payload: OK")
        if payload.get("batch"):
            fcount = len(payload.get("files") or [])
            print(f"batch: true, files={fcount}")
        else:
            print(f"filename: {payload.get('filename')}")
    else:
        print("payload: NOT_FOUND")

    if files:
        print("job_files:")
        for f in files:
            print(f"- {f.get('name')} ({f.get('size')} bytes) sha256={f.get('sha256')}")
    else:
        print("job_files: (none)")

    if llm_costs:
        print("llm_costs:")
        for row in llm_costs:
            print(
                "- model={model} input={input_tokens} output={output_tokens} cost={total_cost_usd}".format(
                    **{k: (row.get(k) or "") for k in ["model", "input_tokens", "output_tokens", "total_cost_usd"]}
                )
            )
    else:
        print("llm_costs: (no rows)")

    print(f"Отчёт записан: {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
