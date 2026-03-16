#!/usr/bin/env python
"""Smoke checks for iikoServer RMS endpoint connectivity and auth/import access."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from app.iiko.auth import AUTH_MODES, build_auth_candidates, extract_auth_result, snippet
except ModuleNotFoundError:
    # Allow direct script execution from outside repo root.
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from app.iiko.auth import AUTH_MODES, build_auth_candidates, extract_auth_result, snippet


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CheckResult:
    name: str
    status: str  # pass | warn | fail
    detail: str
    http_status: int | None = None


def _add(results: list[CheckResult], name: str, status: str, detail: str, http_status: int | None = None) -> None:
    results.append(CheckResult(name=name, status=status, detail=detail, http_status=http_status))


def _build_probe_payload() -> dict[str, Any]:
    return {
        "documentNumber": f"SMOKE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "dateIncoming": datetime.now().strftime("%d.%m.%Y"),
        "status": "NEW",
        "items": {"item": []},
    }


def run_smoke(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    results: list[CheckResult] = []
    auth_headers: dict[str, str] = {}
    key_token: str | None = None

    if not args.base_url:
        _add(results, "config", "fail", "Missing --base-url (or IIKO_SERVER_BASE_URL).")
        return 2, _build_report(args, results)

    if not args.username or not args.password:
        _add(results, "config", "fail", "Missing username/password (use args or IIKO_USERNAME/IIKO_PASSWORD).")
        return 2, _build_report(args, results)

    try:
        with httpx.Client(
            base_url=args.base_url.rstrip("/"),
            verify=args.verify_ssl,
            timeout=args.timeout_sec,
            follow_redirects=True,
        ) as client:
            # 1) Reachability
            try:
                resp_root = client.get("/")
                if resp_root.status_code < 500:
                    _add(
                        results,
                        "reachability",
                        "pass",
                        "Base URL reachable.",
                        http_status=resp_root.status_code,
                    )
                else:
                    _add(
                        results,
                        "reachability",
                        "fail",
                        f"Base URL returned server error: {resp_root.status_code}",
                        http_status=resp_root.status_code,
                    )
            except Exception as exc:  # noqa: BLE001
                _add(results, "reachability", "fail", f"Base URL request failed: {exc}")
                return 2, _build_report(args, results)

            # 2) Auth
            auth_result = None
            auth_errors: list[str] = []
            for candidate in build_auth_candidates(
                username=args.username,
                password=args.password,
                mode=args.auth_mode,
            ):
                try:
                    auth_resp = client.post(args.auth_path, **candidate.request_kwargs())
                except Exception as exc:  # noqa: BLE001
                    auth_errors.append(f"{candidate.name}: request-error: {exc}")
                    continue

                if auth_resp.status_code >= 400:
                    auth_errors.append(
                        f"{candidate.name}: HTTP {auth_resp.status_code}: {snippet(auth_resp.text, 200)}",
                    )
                    continue

                auth_result = extract_auth_result(auth_resp)
                auth_headers = auth_result.bearer_headers
                key_token = auth_result.key_token
                details = [f"Auth succeeded via {candidate.name}."]
                if auth_result.token_source:
                    details.append(f"Token source: {auth_result.token_source}.")
                if key_token:
                    details.append('Using token in "key" query parameter for probes.')
                elif auth_result.has_cookie_session:
                    details.append("Using cookie session for probes.")
                else:
                    details.append("No token/cookie found; next probe may fail with 401.")

                _add(
                    results,
                    "auth",
                    "pass",
                    " ".join(details),
                    http_status=auth_resp.status_code,
                )
                break

            if not auth_result:
                details = " | ".join(auth_errors[-5:]) if auth_errors else "No auth attempts executed."
                _add(results, "auth", "fail", f"Auth failed. {details}")
                return 2, _build_report(args, results)

            # 3) Import access probe (non-destructive intent; usually validation error is expected)
            if not args.skip_import_probe:
                probe_payload = _build_probe_payload()
                request_kwargs: dict[str, Any] = {}
                if auth_headers:
                    request_kwargs["headers"] = auth_headers
                if key_token:
                    request_kwargs["params"] = {"key": key_token}

                try:
                    import_resp = client.post(args.import_path, json=probe_payload, **request_kwargs)
                    status = import_resp.status_code
                    body = snippet(import_resp.text)
                    if status in {200, 201, 202}:
                        _add(results, "import_probe", "pass", "Import endpoint accepted probe payload.", status)
                    elif status in {400, 422}:
                        _add(
                            results,
                            "import_probe",
                            "pass",
                            f"Import endpoint reachable; validation-style response ({status}). Body: {body}",
                            status,
                        )
                    elif status in {401, 403, 404}:
                        auth_hint = (
                            ' (token expected in "key" query parameter)'
                            if not key_token
                            else ""
                        )
                        _add(
                            results,
                            "import_probe",
                            "fail",
                            f"Import endpoint access failed ({status}){auth_hint}. Body: {body}",
                            status,
                        )
                    elif status >= 500:
                        _add(
                            results,
                            "import_probe",
                            "fail",
                            f"Import endpoint server error ({status}). Body: {body}",
                            status,
                        )
                    else:
                        _add(
                            results,
                            "import_probe",
                            "warn",
                            f"Unexpected import response ({status}). Body: {body}",
                            status,
                        )
                except Exception as exc:  # noqa: BLE001
                    _add(results, "import_probe", "fail", f"Import probe request error: {exc}")

    except Exception as exc:  # noqa: BLE001
        _add(results, "runtime", "fail", f"Unexpected runtime error: {exc}")

    report = _build_report(args, results)
    exit_code = 0 if not any(item.status == "fail" for item in results) else 2
    return exit_code, report


def _build_report(args: argparse.Namespace, results: list[CheckResult]) -> dict[str, Any]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": {
            "base_url": args.base_url,
            "auth_path": args.auth_path,
            "auth_mode": args.auth_mode,
            "import_path": args.import_path,
            "verify_ssl": args.verify_ssl,
        },
        "summary": counts,
        "checks": [asdict(r) for r in results],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke checks for iikoServer endpoint auth/import access.",
    )
    parser.add_argument("--base-url", default=os.getenv("IIKO_SERVER_BASE_URL", ""))
    parser.add_argument("--username", default=os.getenv("IIKO_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("IIKO_PASSWORD", ""))
    parser.add_argument("--auth-path", default=os.getenv("IIKO_SERVER_AUTH_PATH", "/resto/api/auth"))
    parser.add_argument(
        "--auth-mode",
        default=os.getenv("IIKO_SERVER_AUTH_MODE", "auto"),
        choices=AUTH_MODES,
    )
    parser.add_argument(
        "--import-path",
        default=os.getenv("IIKO_SERVER_IMPORT_PATH", "/resto/api/documents/import/incomingInvoice"),
    )
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--verify-ssl", action="store_true", default=_env_bool("IIKO_SERVER_VERIFY_SSL", False))
    parser.add_argument("--skip-import-probe", action="store_true")
    parser.add_argument("--report-file", default="logs/iiko_smoke_last.json")
    return parser


def main() -> int:
    args = _parser().parse_args()
    exit_code, report = run_smoke(args)

    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nReport saved: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
