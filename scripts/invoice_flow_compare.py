"""Quick side-by-side runner for legacy/shadow/modular invoice flow modes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas import InvoiceItem
from app.services.invoice_flow import InvoiceFlowRunner


def _load_items(path: Path) -> list[InvoiceItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        payload = raw["items"]
    elif isinstance(raw, list):
        payload = raw
    else:
        raise ValueError("Expected JSON list or object with `items` key")
    return [InvoiceItem.model_validate(item) for item in payload]


def _print_mode(mode: str, items: list[InvoiceItem]) -> None:
    result = InvoiceFlowRunner(mode=mode).execute(items)
    print(f"[{mode}] changed_rows={result.changed_rows} warnings={len(result.warnings)}")
    for idx, item in enumerate(result.output_items, start=1):
        qty = item.supply_quantity or item.unit_amount
        print(f"  {idx:02d}. {item.name} | qty={qty} | unit={item.unit_measure}")
    if result.mode == "shadow":
        print("  shadow preview:")
        for idx, item in enumerate(result.modular_items, start=1):
            qty = item.supply_quantity or item.unit_amount
            print(f"    {idx:02d}. {item.name} | qty={qty} | unit={item.unit_measure}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, default="", help="Path to JSON with items")
    parser.add_argument("--request-id", type=str, default="", help="Request id from logs/requests/<id>.json")
    args = parser.parse_args()

    if not args.json and not args.request_id:
        print("Provide --json <path> or --request-id <id>")
        return 2

    if args.json:
        source_path = Path(args.json).expanduser().resolve()
    else:
        source_path = (PROJECT_ROOT / "logs" / "requests" / f"{args.request_id}.json").resolve()

    if not source_path.exists():
        print(f"File not found: {source_path}")
        return 2

    try:
        items = _load_items(source_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load items: {exc}")
        return 1

    print(f"Loaded rows: {len(items)} from {source_path}")
    for mode in ("legacy", "shadow", "modular"):
        _print_mode(mode, items)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
