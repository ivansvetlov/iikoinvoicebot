"""Compare SotaOCR transcription vs main invoice pipeline on the same file."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.html_table import html_tables_to_text
from app.ocr.sotaocr_client import SotaOcrClient
from app.ocr.vpn import ensure_api_vpn
from app.parsers.invoice_parser import InvoiceParser
from app.schemas import InvoiceItem, InvoiceParseResult
from app.services.invoice_validator import is_likely_invoice
from app.services.pipeline import InvoicePipelineService

INVOICE_NO_RE = re.compile(r"(?:номер документа|накладная)\D*(\d{4,})", re.I)
DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
TOTAL_RE = re.compile(r"57\s*804[,.]50|57804[,.]50")

def _item_brief(item: InvoiceItem) -> dict[str, str | None]:
    return {
        "name": (item.name or "")[:80],
        "qty": str(item.unit_amount or item.supply_quantity or ""),
        "price": str(item.unit_price or ""),
        "total": str(item.total_cost or item.cost_with_tax or ""),
        "tax_rate": str(item.tax_rate or ""),
    }


def _serialize_pipeline(parsed: InvoiceParseResult) -> dict:
    return {
        "invoice_number": parsed.invoice_number,
        "invoice_date": parsed.invoice_date,
        "vendor_name": parsed.vendor_name,
        "total_amount": str(parsed.total_amount) if parsed.total_amount is not None else None,
        "items_count": len(parsed.items),
        "items": [_item_brief(item) for item in parsed.items],
        "warnings": parsed.warnings,
    }


def _check_sotaocr_requirements(raw: str, plain: str, items: list[InvoiceItem]) -> list[str]:
    checks: list[str] = []
    if "ТОВАРНАЯ НАКЛАДНАЯ" in raw.upper():
        checks.append("ok: document title detected")
    else:
        checks.append("fail: missing 'ТОВАРНАЯ НАКЛАДНАЯ'")

    if INVOICE_NO_RE.search(raw) or "40066787" in raw:
        checks.append("ok: invoice number 40066787 present")
    else:
        checks.append("fail: invoice number not found")

    if DATE_RE.search(raw):
        checks.append(f"ok: date present ({DATE_RE.search(raw).group(1)})")
    else:
        checks.append("fail: invoice date missing")

    data_rows = [line for line in plain.splitlines() if re.match(r"^\d{3,5}\s", line)]
    if len(data_rows) >= 5:
        checks.append(f"ok: {len(data_rows)} product rows in table")
    else:
        checks.append(f"warn: only {len(data_rows)} product-like rows")

    if TOTAL_RE.search(raw.replace(" ", "")):
        checks.append("ok: document total 57804.50 visible")
    else:
        checks.append("warn: total 57804.50 not matched exactly")

    ocr_typos = ("зиказ", "Диница", "игрудки", "вочищ", "Бенгрия", "12 47,00")
    hits = [typo for typo in ocr_typos if typo in raw]
    if hits:
        checks.append(f"warn: OCR typos: {', '.join(hits)}")

    parsed_probe = InvoiceParseResult(source_type="text", raw_text=plain, items=items)
    llm_data = {"document_type": "TORG-12", "has_invoice_keyword": True}
    if is_likely_invoice(items, plain, parsed_probe, "text", llm_data):
        checks.append(f"ok: validator accepts invoice ({len(items)} parsed items)")
    else:
        checks.append(f"fail: validator rejected parsed items ({len(items)} items)")

    return checks


def _diff_items(left_items: list[InvoiceItem], right_items: list[InvoiceItem]) -> list[str]:
    notes: list[str] = []
    notes.append(f"left items: {len(left_items)}, right items: {len(right_items)}")
    for idx, left in enumerate(left_items[:10], start=1):
        name_key = (left.name or "")[:30].lower()
        match = next(
            (
                right
                for right in right_items
                if (right.name or "")[:30].lower() in name_key
                or name_key in (right.name or "")[:30].lower()
            ),
            None,
        )
        if not match:
            notes.append(f"row {idx}: left only -> {(left.name or '')[:50]}")
            continue
        diffs: list[str] = []
        for field in ("unit_amount", "unit_price", "total_cost"):
            l_val = getattr(left, field, None)
            r_val = getattr(match, field, None)
            if l_val is not None and r_val is not None and l_val != r_val:
                diffs.append(f"{field} {l_val} vs {r_val}")
        if diffs:
            notes.append(f"row {idx}: value diff -> {'; '.join(diffs)}")
        else:
            notes.append(f"row {idx}: match -> {(left.name or '')[:45]}")
    return notes


async def _run(path: Path, *, use_cached_sota: Path | None, skip_pipeline: bool) -> int:
    ensure_api_vpn(raise_on_failure=True)
    content = path.read_bytes()
    out_dir = ROOT / "logs" / "sotaocr_compare"
    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline = InvoicePipelineService()

    if skip_pipeline:
        pipeline_result = None
        pipeline_data = {"skipped": True}
        print("=== main pipeline (skipped) ===")
    else:
        print("=== main pipeline (OpenAI vision) ===")
        pipeline_result = await pipeline.process(
            path.name,
            content,
            push_to_iiko=False,
            user_id="compare-script",
        )
        pipeline_data = {
            **_serialize_pipeline(pipeline_result.parsed),
            "status": pipeline_result.status,
            "error_code": pipeline_result.error_code,
            "message": pipeline_result.message,
        }
    (out_dir / "pipeline.json").write_text(
        json.dumps(pipeline_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(pipeline_data, ensure_ascii=False, indent=2))

    print("\n=== sotaocr ===")
    if use_cached_sota and use_cached_sota.is_file():
        sota_raw = use_cached_sota.read_text(encoding="utf-8")
        print(f"using cached OCR: {use_cached_sota}")
    else:
        client = SotaOcrClient()
        _, result = await client.extract_text(content, path.name, result_format="text")
        sota_raw = result.content
        (out_dir / "sotaocr_raw.txt").write_text(sota_raw, encoding="utf-8")

    sota_plain = html_tables_to_text(sota_raw)
    (out_dir / "sotaocr_plain.txt").write_text(sota_plain, encoding="utf-8")
    sota_items, sota_warnings = InvoiceParser.parse_items(sota_plain)
    sota_data = {
        "raw_chars": len(sota_raw),
        "plain_chars": len(sota_plain),
        "parser_warnings": sota_warnings,
        "items_count": len(sota_items),
        "items": [_item_brief(item) for item in sota_items],
        "requirements": _check_sotaocr_requirements(sota_raw, sota_plain, sota_items),
    }
    (out_dir / "sotaocr.json").write_text(
        json.dumps(sota_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(sota_data, ensure_ascii=False, indent=2))

    print("\n=== hybrid (sotaocr text -> OpenAI) ===")
    hybrid_llm = await pipeline._call_llm(
        pipeline._build_prompt(_HYBRID_PROMPT, sota_plain),
        "text",
        "sotaocr_plain.txt",
        sota_plain.encode("utf-8"),
        sota_plain,
    )
    hybrid_items = pipeline._build_items_from_llm(hybrid_llm)
    hybrid_data = {
        "invoice_number": hybrid_llm.get("invoice_number"),
        "invoice_date": hybrid_llm.get("invoice_date"),
        "vendor_name": hybrid_llm.get("vendor_name"),
        "total_amount": hybrid_llm.get("total_amount"),
        "items_count": len(hybrid_items),
        "items": [_item_brief(item) for item in hybrid_items],
    }
    (out_dir / "hybrid.json").write_text(
        json.dumps(hybrid_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(hybrid_data, ensure_ascii=False, indent=2))

    print("\n=== comparison ===")
    pipeline_items = pipeline_result.parsed.items if pipeline_result else []
    comparison = {
        "pipeline_status": pipeline_result.status if pipeline_result else "skipped",
        "pipeline_error": pipeline_result.error_code if pipeline_result else None,
        "pipeline_total": pipeline_data.get("total_amount"),
        "pipeline_items_count": len(pipeline_items),
        "sota_parser_items_count": len(sota_items),
        "hybrid_items_count": len(hybrid_items),
        "hybrid_total": hybrid_data.get("total_amount"),
        "pipeline_vs_hybrid": _diff_items(pipeline_items, hybrid_items),
        "parser_vs_hybrid": _diff_items(sota_items, hybrid_items),
    }
    (out_dir / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for section in ("pipeline_vs_hybrid", "parser_vs_hybrid"):
        print(f"[{section}]")
        for line in comparison[section]:
            print(line)
    print(f"\nsaved: {out_dir.relative_to(ROOT)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Invoice image/pdf path")
    parser.add_argument(
        "--cached-sota",
        default="",
        help="Optional cached SotaOCR text path (skip API call); empty = live OCR",
    )
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Skip slow OpenAI vision pipeline (SOTA + hybrid only)",
    )
    args = parser.parse_args()
    cached = Path(args.cached_sota) if args.cached_sota else None
    raise SystemExit(
        asyncio.run(_run(Path(args.file), use_cached_sota=cached, skip_pipeline=args.skip_pipeline))
    )


if __name__ == "__main__":
    main()
