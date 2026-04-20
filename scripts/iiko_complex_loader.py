"""Stress scenarios for iiko incoming invoice import using parsed-like items.

Usage:
    .venv\\Scripts\\python.exe scripts\\iiko_complex_loader.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.iiko.server_client import IikoServerClient, IikoUploadResult
from app.schemas import InvoiceItem


@dataclass(slots=True)
class Scenario:
    name: str
    description: str
    invoice_status: str
    default_supplier_id: str
    items: list[InvoiceItem]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_runtime_settings() -> dict[str, Any]:
    base_url = os.getenv("IIKO_API_BASE_URL") or settings.iiko_api_base_url or "https://840-786-070.iiko.it"
    username = os.getenv("IIKO_USERNAME") or settings.iiko_username or "user"
    password = os.getenv("IIKO_PASSWORD") or settings.iiko_password or "user#test"
    verify_tls = _bool_env("IIKO_API_VERIFY_TLS", False)
    return {
        "base_url": base_url.rstrip("/"),
        "username": username,
        "password": password,
        "verify_tls": verify_tls,
    }


def _auth_token(base_url: str, username: str, password: str, verify_tls: bool) -> str:
    password_hash = hashlib.sha1(password.encode("utf-8")).hexdigest()
    with httpx.Client(timeout=30, verify=verify_tls) as client:
        response = client.post(
            f"{base_url}/resto/api/auth",
            data={"login": username, "pass": password_hash},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"auth failed: {response.status_code} {response.text[:300]}")
        token = response.text.strip().strip('"').strip("'")
        if not token:
            raise RuntimeError("auth failed: empty token")
        return token


def _fetch_products(base_url: str, token: str, verify_tls: bool) -> list[dict[str, Any]]:
    with httpx.Client(timeout=30, verify=verify_tls) as client:
        response = client.get(
            f"{base_url}/resto/api/v2/entities/products/list",
            params={"key": token, "includeDeleted": "false"},
            cookies={"key": token},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"products/list failed: {response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]


def _fetch_store_ids(base_url: str, token: str, verify_tls: bool) -> list[str]:
    with httpx.Client(timeout=30, verify=verify_tls) as client:
        response = client.get(
            f"{base_url}/resto/api/corporation/stores",
            params={"key": token, "revisionFrom": "-1"},
            cookies={"key": token},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"corporation/stores failed: {response.status_code} {response.text[:300]}")
        root = ET.fromstring(response.text)
        store_ids: list[str] = []
        for node in root.findall(".//corporateItemDto"):
            item_id = (node.findtext("id") or "").strip()
            item_type = (node.findtext("type") or "").strip().upper()
            if item_id and (not item_type or item_type == "STORE"):
                store_ids.append(item_id)
        if not store_ids:
            raise RuntimeError("no stores returned by corporation/stores")
        return store_ids


def _fetch_employee_ids(base_url: str, token: str, verify_tls: bool) -> list[str]:
    with httpx.Client(timeout=30, verify=verify_tls) as client:
        response = client.get(
            f"{base_url}/resto/api/employees",
            params={"key": token},
            cookies={"key": token},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"employees failed: {response.status_code} {response.text[:300]}")
        root = ET.fromstring(response.text)
        employee_ids: list[str] = []
        for node in root.findall(".//employee"):
            item_id = (node.findtext("id") or "").strip()
            if item_id:
                employee_ids.append(item_id)
        if not employee_ids:
            raise RuntimeError("no employees returned by /employees")
        return employee_ids


def _pick_products(products: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], str]:
    goods = [p for p in products if str(p.get("type") or "").upper() == "GOODS"]
    services = [p for p in products if str(p.get("type") or "").upper() == "SERVICE"]
    if not goods:
        raise RuntimeError("no GOODS products found; create one product first")
    if not services:
        raise RuntimeError("no SERVICE products found; expected at least one")

    names = [str(p.get("name") or "").strip() for p in goods]
    counts = Counter(name for name in names if name)
    ambiguous_name = ""
    for name, count in counts.items():
        if count >= 2:
            ambiguous_name = name
            break
    if not ambiguous_name:
        ambiguous_name = str(goods[0].get("name") or "")
    return goods[0], services[0], ambiguous_name


def _build_scenarios(
    store_id: str,
    default_supplier_id: str,
    goods: dict[str, Any],
    service: dict[str, Any],
    ambiguous_name: str,
) -> list[Scenario]:
    goods_id = str(goods.get("id") or "")
    goods_name = str(goods.get("name") or "")
    goods_article = str(goods.get("num") or "")
    service_id = str(service.get("id") or "")
    service_name = str(service.get("name") or "")
    service_article = str(service.get("num") or "")

    scenarios: list[Scenario] = [
        Scenario(
            name="processed_goods_ok",
            description="Happy-path: mapped GOODS + supplier + PROCESSED",
            invoice_status="PROCESSED",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name=goods_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("7"),
                    cost_without_tax=Decimal("7"),
                    cost_with_tax=Decimal("7"),
                    extras={
                        "product": goods_id,
                        "productArticle": goods_article,
                        "store": store_id,
                    },
                )
            ],
        ),
        Scenario(
            name="processed_goods_without_supplier",
            description="Posting without supplier should fail",
            invoice_status="PROCESSED",
            default_supplier_id="",
            items=[
                InvoiceItem(
                    name=goods_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("5"),
                    cost_without_tax=Decimal("5"),
                    cost_with_tax=Decimal("5"),
                    extras={
                        "product": goods_id,
                        "productArticle": goods_article,
                        "store": store_id,
                    },
                )
            ],
        ),
        Scenario(
            name="new_goods_without_supplier",
            description="Draft (NEW) can be created without supplier",
            invoice_status="NEW",
            default_supplier_id="",
            items=[
                InvoiceItem(
                    name=goods_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("3"),
                    cost_without_tax=Decimal("3"),
                    cost_with_tax=Decimal("3"),
                    extras={
                        "product": goods_id,
                        "productArticle": goods_article,
                        "store": store_id,
                    },
                )
            ],
        ),
        Scenario(
            name="new_unmapped_unknown_name",
            description="Unknown name without ids should fail in auto-resolve",
            invoice_status="NEW",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name="Совсем неизвестный товар API stress",
                    unit_amount=Decimal("2"),
                    unit_price=Decimal("11"),
                    cost_without_tax=Decimal("22"),
                    cost_with_tax=Decimal("22"),
                    extras={},
                )
            ],
        ),
        Scenario(
            name="new_ambiguous_name_mapping",
            description="Duplicate name in catalog should fail mapping as ambiguous",
            invoice_status="NEW",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name=ambiguous_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("1"),
                    cost_without_tax=Decimal("1"),
                    cost_with_tax=Decimal("1"),
                    extras={},
                )
            ],
        ),
        Scenario(
            name="new_invalid_store_guid",
            description="Invalid store id should fail import validation",
            invoice_status="NEW",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name=goods_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("4"),
                    cost_without_tax=Decimal("4"),
                    cost_with_tax=Decimal("4"),
                    extras={
                        "product": goods_id,
                        "productArticle": goods_article,
                        "store": "00000000-0000-0000-0000-000000000000",
                    },
                )
            ],
        ),
        Scenario(
            name="new_negative_amount",
            description="Negative quantity should be rejected by business validation",
            invoice_status="NEW",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name=goods_name,
                    unit_amount=Decimal("-1"),
                    unit_price=Decimal("4"),
                    cost_without_tax=Decimal("-4"),
                    cost_with_tax=Decimal("-4"),
                    extras={
                        "product": goods_id,
                        "productArticle": goods_article,
                        "store": store_id,
                    },
                )
            ],
        ),
        Scenario(
            name="processed_service_only",
            description="Service-only posting: document may be processed, stock verification is skipped",
            invoice_status="PROCESSED",
            default_supplier_id=default_supplier_id,
            items=[
                InvoiceItem(
                    name=service_name,
                    unit_amount=Decimal("1"),
                    unit_price=Decimal("2"),
                    cost_without_tax=Decimal("2"),
                    cost_with_tax=Decimal("2"),
                    extras={
                        "product": service_id,
                        "productArticle": service_article,
                        "store": store_id,
                    },
                )
            ],
        ),
    ]
    return scenarios


@contextmanager
def _override_settings(values: dict[str, Any]):
    snapshot: dict[str, Any] = {}
    for key, value in values.items():
        snapshot[key] = getattr(settings, key)
        setattr(settings, key, value)
    try:
        yield
    finally:
        for key, value in snapshot.items():
            setattr(settings, key, value)


async def _run_scenario(
    scenario: Scenario,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    overrides = {
        "iiko_transport": "api",
        "iiko_api_base_url": runtime["base_url"],
        "iiko_api_verify_tls": runtime["verify_tls"],
        "iiko_incoming_invoice_status": scenario.invoice_status,
        "iiko_default_supplier_id": scenario.default_supplier_id,
        "iiko_verify_upload": True,
        "iiko_verify_stock_balance": True,
        "iiko_autoresolve_products": True,
        "iiko_autofill_store": True,
        "iiko_catalog_cache_sec": 0,
    }

    with _override_settings(overrides):
        client = IikoServerClient()
        try:
            result: IikoUploadResult = await client.upload_invoice_items(
                items=scenario.items,
                username=runtime["username"],
                password=runtime["password"],
            )
            return {
                "scenario": scenario.name,
                "description": scenario.description,
                "outcome": "success",
                "requested_status": result.requested_status,
                "document_number": result.document_number,
                "document_id": result.document_id,
                "exported_status": result.exported_status,
                "stock_verified": result.stock_verified,
                "stock_warning": result.stock_warning,
                "balance_deltas": result.balance_deltas,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "scenario": scenario.name,
                "description": scenario.description,
                "outcome": "error",
                "requested_status": scenario.invoice_status,
                "error": str(exc),
            }


def _write_report(report: dict[str, Any]) -> Path:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = logs_dir / f"iiko_complex_loader_{ts}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


async def main() -> int:
    runtime = _resolve_runtime_settings()
    token = _auth_token(
        base_url=runtime["base_url"],
        username=runtime["username"],
        password=runtime["password"],
        verify_tls=runtime["verify_tls"],
    )
    products = _fetch_products(runtime["base_url"], token, runtime["verify_tls"])
    stores = _fetch_store_ids(runtime["base_url"], token, runtime["verify_tls"])
    employees = _fetch_employee_ids(runtime["base_url"], token, runtime["verify_tls"])
    goods, service, ambiguous_name = _pick_products(products)
    scenarios = _build_scenarios(
        store_id=stores[0],
        default_supplier_id=employees[0],
        goods=goods,
        service=service,
        ambiguous_name=ambiguous_name,
    )

    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        outcome = await _run_scenario(scenario, runtime)
        results.append(outcome)
        if outcome["outcome"] == "success":
            print(
                f"[OK] {scenario.name}: "
                f"doc={outcome.get('document_number')} "
                f"status={outcome.get('exported_status') or outcome.get('requested_status')} "
                f"stock_verified={outcome.get('stock_verified')}"
            )
        else:
            print(f"[ERR] {scenario.name}: {outcome.get('error')}")

    summary = Counter(item["outcome"] for item in results)
    report = {
        "generated_at": datetime.now().isoformat(),
        "runtime": {
            "base_url": runtime["base_url"],
            "username": runtime["username"],
            "verify_tls": runtime["verify_tls"],
        },
        "catalog_stats": {
            "products_total": len(products),
            "stores_total": len(stores),
            "employees_total": len(employees),
            "ambiguous_name_used": ambiguous_name,
        },
        "summary": {
            "success": summary.get("success", 0),
            "error": summary.get("error", 0),
        },
        "results": results,
    }
    report_path = _write_report(report)
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
