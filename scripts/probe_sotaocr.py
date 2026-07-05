"""Probe SotaOCR connectivity and optional file upload.

Usage:
  python scripts/probe_sotaocr.py
  python scripts/probe_sotaocr.py path/to/invoice.jpg
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.sotaocr_client import SotaOcrClient, SotaOcrError
from app.ocr.vpn import ensure_sotaocr_vpn, is_split_tunnel_running


async def _run(file_path: Path | None) -> int:
    out_dir = ROOT / "logs" / "sotaocr_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("0) vpn")
    if ensure_sotaocr_vpn():
        print(f"   ok: split tunnel running ({is_split_tunnel_running()})")
    else:
        print("   warn: split tunnel not running (run scripts/ensure_sotaocr_vpn.ps1 as admin)")

    client = SotaOcrClient()

    print("1) balance")
    try:
        balance = await client.get_balance()
    except SotaOcrError as exc:
        err_path = out_dir / "error.json"
        err_path.write_text(
            json.dumps(
                {
                    "message": str(exc),
                    "status_code": exc.status_code,
                    "code": exc.code,
                    "payload": exc.payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"   failed: {exc}")
        print(f"   details: {err_path.relative_to(ROOT)}")
        return 1

    balance_path = out_dir / "balance.json"
    balance_path.write_text(
        json.dumps(balance.raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"   ok: remaining_pages={balance.remaining_pages}, "
        f"saved={balance_path.relative_to(ROOT)}"
    )

    if file_path is None:
        print("2) upload skipped (pass file path to test OCR)")
        return 0

    if not file_path.is_file():
        print(f"file not found: {file_path}", file=sys.stderr)
        return 2

    print(f"2) upload {file_path.name} ({file_path.stat().st_size} bytes)")
    content = file_path.read_bytes()
    try:
        job, result = await client.extract_text(content, file_path.name, result_format="text")
    except SotaOcrError as exc:
        err_path = out_dir / "error.json"
        err_path.write_text(
            json.dumps(
                {
                    "message": str(exc),
                    "status_code": exc.status_code,
                    "code": exc.code,
                    "payload": exc.payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"   failed: {exc}")
        print(f"   details: {err_path.relative_to(ROOT)}")
        return 1

    (out_dir / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "result.txt").write_text(result.content, encoding="utf-8")
    print(f"   ok: job={job.id}, chars={len(result.content)}")
    print(f"   saved: {out_dir.relative_to(ROOT)}/result.txt")
    preview = result.content[:500].replace("\n", " ")
    if preview:
        print(f"   preview: {preview}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe SotaOCR API")
    parser.add_argument("file", nargs="?", help="Optional invoice image/pdf to OCR")
    args = parser.parse_args()
    file_path = Path(args.file).expanduser() if args.file else None
    raise SystemExit(asyncio.run(_run(file_path)))


if __name__ == "__main__":
    main()
