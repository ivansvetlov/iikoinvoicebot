"""Batch invoice parser via OpenAI function calling.

Example usage:
  python scripts/invoice_llm_client.py --path ./invoices --model gpt-4o-mini

Environment:
  OPENAI_API_KEY=... (read from .env or environment)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def load_env(path: Path) -> None:
    """Load key=value pairs from .env into os.environ if not already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in os.environ:
            os.environ[key] = value


def encode_file(path: Path) -> str:
    """Read file and return base64 string."""
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def detect_file_type(path: Path) -> str:
    """Detect file type based on suffix for the JSON payload."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"}:
        return "image"
    raise ValueError(f"Unsupported file type: {suffix}")


def build_function_schema() -> dict[str, Any]:
    """Build the function calling schema for parse_invoice."""
    return {
        "name": "parse_invoice",
        "description": "Extract invoice metadata and line items from a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "invoice_date": {"type": "string"},
                "vendor_name": {"type": "string"},
                "total_amount": {"type": "number"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                            "line_total": {"type": "number"},
                        },
                        "required": ["description", "quantity", "unit_price", "line_total"],
                    },
                },
            },
            "required": ["invoice_number", "invoice_date", "vendor_name", "total_amount", "items"],
        },
    }


def build_input(prompt: str, file_type: str, file_b64: str, filename: str) -> list[dict[str, Any]]:
    """Build OpenAI Responses API input with text + file/image."""
    if file_type == "image":
        # data URL with MIME type inferred from filename
        ext = Path(filename).suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
        image_url = f"data:{mime};base64,{file_b64}"
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ]

    if file_type == "pdf":
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": file_b64,
                    },
                ],
            }
        ]

    raise ValueError(f"Unsupported file type: {file_type}")


def call_openai(
    api_key: str,
    model: str,
    prompt: str,
    path: Path,
) -> dict[str, Any] | None:
    """Call OpenAI Responses API and return function args if present."""
    file_type = detect_file_type(path)
    file_b64 = encode_file(path)

    payload = {
        "model": model,
        "input": build_input(prompt, file_type, file_b64, path.name),
        "tools": [
            {
                "type": "function",
                **build_function_schema(),
            }
        ],
        "tool_choice": {"type": "function", "name": "parse_invoice"},
    }

    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }

    with httpx.Client(timeout=120) as client:
        response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    # Find the function call output
    outputs = data.get("output", [])
    for item in outputs:
        if item.get("type") == "function_call" and item.get("name") == "parse_invoice":
            return item.get("arguments")

    return None


def collect_files(path: Path) -> list[Path]:
    """Collect files from a single path or a directory."""
    if path.is_file():
        return [path]
    if path.is_dir():
        files: list[Path] = []
        for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp", "*.tiff"):
            files.extend(path.rglob(ext))
        return sorted(files)
    raise FileNotFoundError(f"Path not found: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse invoices with OpenAI function calling.")
    parser.add_argument("--path", required=True, help="File path or directory with invoices")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model name")
    parser.add_argument(
        "--prompt",
        default=(
            "Extract invoice data and return only the function call with JSON. "
            "If a field is missing, return null."
        ),
        help="Instruction prompt for the LLM",
    )
    args = parser.parse_args()

    load_env(Path(".env"))
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    input_path = Path(args.path)
    try:
        files = collect_files(input_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    for path in files:
        try:
            parsed = call_openai(api_key, args.model, args.prompt, path)
        except (ValueError, OSError) as exc:
            print(f"Error reading {path}: {exc}", file=sys.stderr)
            continue
        except httpx.RequestError as exc:
            print(f"Network error for {path}: {exc}", file=sys.stderr)
            continue
        except httpx.HTTPStatusError as exc:
            print(f"HTTP error for {path}: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
            continue

        if parsed is None:
            print(f"Warning: no function call returned for {path}", file=sys.stderr)
            continue

        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                print(f"Warning: function call args not JSON for {path}", file=sys.stderr)
                continue

        results.append(parsed)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
