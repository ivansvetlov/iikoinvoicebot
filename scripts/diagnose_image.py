"""Diagnostics runner for document recognition on one file or a folder.

Usage:
  .venv\\Scripts\\python.exe scripts/diagnose_image.py --path "doc templates\\58691991.jpeg"
  .venv\\Scripts\\python.exe scripts/diagnose_image.py --path "doc templates" --repeat 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.parsers.file_text_extractor import FileTextExtractor
from app.services.pipeline import InvoicePipelineService

REQUESTS_DIR = PROJECT_ROOT / "logs" / "requests"
TMP_DIR = PROJECT_ROOT / "tmp"


def _read_request_payload(request_id: str | None) -> dict[str, Any] | None:
    if not request_id:
        return None
    path = REQUESTS_DIR / f"{request_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _image_meta(content: bytes) -> dict[str, Any]:
    # Pillow can load from bytes via BytesIO. Avoid importing io globally for small script.
    from io import BytesIO

    with Image.open(BytesIO(content)) as img:
        return {
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
            "format": img.format,
        }


@dataclass
class RunResult:
    run: int
    status: str
    error_code: str | None
    message: str | None
    request_id: str | None
    source_type: str | None
    items_count: int
    elapsed_sec: float
    document_type: str | None = None
    has_invoice_keyword: bool | None = None
    has_receipt_keyword: bool | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor_name: str | None = None
    total_amount: str | None = None


async def _run_once(
    service: InvoicePipelineService,
    file_path: Path,
    run_no: int,
) -> RunResult:
    content = file_path.read_bytes()
    t0 = perf_counter()
    response = await service.process(file_path.name, content, push_to_iiko=False, user_id="diagnose-image")
    elapsed = round(perf_counter() - t0, 2)

    payload = _read_request_payload(response.request_id)
    return RunResult(
        run=run_no,
        status=response.status,
        error_code=response.error_code,
        message=response.message,
        request_id=response.request_id,
        source_type=response.parsed.source_type,
        items_count=len(response.parsed.items),
        elapsed_sec=elapsed,
        document_type=(payload or {}).get("document_type"),
        has_invoice_keyword=(payload or {}).get("has_invoice_keyword"),
        has_receipt_keyword=(payload or {}).get("has_receipt_keyword"),
        invoice_number=response.parsed.invoice_number,
        invoice_date=response.parsed.invoice_date,
        vendor_name=response.parsed.vendor_name,
        total_amount=str(response.parsed.total_amount) if response.parsed.total_amount is not None else None,
    )


def _iter_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = [p for p in sorted(path.iterdir()) if p.is_file()]
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".pdf", ".docx", ".xls", ".xlsx", ".txt", ".csv"}
    return [p for p in files if p.suffix.lower() in allowed]


async def diagnose(path: Path, repeat: int) -> dict[str, Any]:
    service = InvoicePipelineService()
    files = _iter_files(path)
    report_rows: list[dict[str, Any]] = []

    for file_path in files:
        content = file_path.read_bytes()
        source_type = FileTextExtractor.detect_source_type(file_path.name)
        row: dict[str, Any] = {
            "file": str(file_path),
            "name": file_path.name,
            "size_bytes": len(content),
            "source_type": source_type,
            "runs": [],
        }

        if source_type == "image":
            try:
                row["raw_image"] = _image_meta(content)
            except Exception as exc:
                row["raw_image_error"] = f"{exc.__class__.__name__}: {exc}"
            try:
                prepared_name, prepared_bytes, ocr_text = service._prepare_image_payload(file_path.name, content)
                row["prepared_name"] = prepared_name
                row["prepared_bytes"] = len(prepared_bytes)
                row["ocr_chars"] = len(ocr_text or "")
                row["ocr_lines"] = len((ocr_text or "").splitlines())
                row["looks_like_receipt_text"] = service._looks_like_receipt_text(ocr_text or "")
            except Exception as exc:
                row["prepare_error"] = f"{exc.__class__.__name__}: {exc}"

        for run_no in range(1, repeat + 1):
            try:
                run_result = await _run_once(service, file_path, run_no)
                row["runs"].append(asdict(run_result))
            except Exception as exc:
                row["runs"].append(
                    {
                        "run": run_no,
                        "status": "exception",
                        "error_code": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )

        report_rows.append(row)

    ok = 0
    errors = 0
    for row in report_rows:
        for run in row["runs"]:
            if run.get("status") == "ok":
                ok += 1
            else:
                errors += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "path": str(path),
        "files_count": len(files),
        "repeat": repeat,
        "ok_runs": ok,
        "error_runs": errors,
        "rows": report_rows,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose document recognition quality.")
    parser.add_argument("--path", required=True, help="File path or folder with documents")
    parser.add_argument("--repeat", type=int, default=1, help="How many times to process each file")
    parser.add_argument("--out", default="", help="Optional output JSON path")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        raise SystemExit(f"Path does not exist: {target}")
    repeat = max(1, args.repeat)

    report = asyncio.run(diagnose(target, repeat))

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = target.name.replace(" ", "_")
        out_path = TMP_DIR / f"diagnose_image_{safe_name}_{stamp}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved: {out_path}")
    print(f"Files: {report['files_count']}, repeat: {report['repeat']}")
    print(f"Runs ok: {report['ok_runs']}, runs error: {report['error_runs']}")


if __name__ == "__main__":
    main()
