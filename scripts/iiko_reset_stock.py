"""Reset non-zero stock balances on iiko demo stand via outgoing invoices.

Default mode is dry-run.
Use --apply to execute write-off documents.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET

import httpx


@dataclass(slots=True)
class BalanceRow:
    store_id: str
    store_name: str
    product_id: str
    product_name: str
    amount: Decimal
    total_sum: Decimal


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--verify-tls", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--delete-products", action="store_true", default=False)
    return parser.parse_args()


def _auth(client: httpx.Client, base_url: str, login: str, password: str) -> str:
    password_hash = hashlib.sha1(password.encode("utf-8")).hexdigest()
    resp = client.post(
        f"{base_url.rstrip('/')}/resto/api/auth",
        data={"login": login, "pass": password_hash},
    )
    resp.raise_for_status()
    token = resp.text.strip().strip('"').strip("'")
    if not token:
        raise RuntimeError("Empty auth token")
    return token


def _employee_id(client: httpx.Client, base_url: str, token: str) -> str:
    resp = client.get(
        f"{base_url.rstrip('/')}/resto/api/employees",
        params={"key": token},
        cookies={"key": token},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    employee_id = (root.findtext(".//employee/id") or "").strip()
    if not employee_id:
        raise RuntimeError("No employee id found for outgoingInvoice counteragentId")
    return employee_id


def _stores(client: httpx.Client, base_url: str, token: str) -> list[tuple[str, str]]:
    resp = client.get(
        f"{base_url.rstrip('/')}/resto/api/corporation/stores",
        params={"key": token, "revisionFrom": "-1"},
        cookies={"key": token},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: list[tuple[str, str]] = []
    for node in root.findall(".//corporateItemDto"):
        node_type = (node.findtext("type") or "").strip().upper()
        if node_type and node_type != "STORE":
            continue
        store_id = (node.findtext("id") or "").strip()
        store_name = (node.findtext("name") or "").strip()
        if store_id:
            out.append((store_id, store_name))
    return out


def _goods(client: httpx.Client, base_url: str, token: str) -> list[tuple[str, str]]:
    resp = client.get(
        f"{base_url.rstrip('/')}/resto/api/v2/entities/products/list",
        params={"key": token, "includeDeleted": "false"},
        cookies={"key": token},
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload if isinstance(payload, list) else []
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().upper() != "GOODS":
            continue
        product_id = str(row.get("id") or "").strip()
        product_name = str(row.get("name") or "").strip()
        if product_id:
            out.append((product_id, product_name))
    return out


def _all_products(client: httpx.Client, base_url: str, token: str) -> list[tuple[str, str]]:
    resp = client.get(
        f"{base_url.rstrip('/')}/resto/api/v2/entities/products/list",
        params={"key": token, "includeDeleted": "false"},
        cookies={"key": token},
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload if isinstance(payload, list) else []
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product_id = str(row.get("id") or "").strip()
        product_name = str(row.get("name") or "").strip()
        if product_id:
            out.append((product_id, product_name))
    return out


def _delete_products(client: httpx.Client, base_url: str, token: str, product_ids: list[str]) -> None:
    if not product_ids:
        return
    payload = {"items": [{"id": product_id} for product_id in product_ids]}
    resp = client.post(
        f"{base_url.rstrip('/')}/resto/api/v2/entities/products/delete",
        params={"key": token},
        cookies={"key": token},
        json=payload,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Products delete failed: {resp.status_code} {resp.text[:300]}")


def _balances(
    client: httpx.Client,
    base_url: str,
    token: str,
    stores: list[tuple[str, str]],
    products: list[tuple[str, str]],
) -> list[BalanceRow]:
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out: list[BalanceRow] = []
    for store_id, store_name in stores:
        for product_id, product_name in products:
            resp = client.get(
                f"{base_url.rstrip('/')}/resto/api/v2/reports/balance/stores",
                params={
                    "key": token,
                    "timestamp": ts,
                    "store": store_id,
                    "product": product_id,
                },
                cookies={"key": token},
            )
            if resp.status_code >= 400:
                continue
            rows = resp.json() if "json" in resp.headers.get("content-type", "").lower() else []
            if not isinstance(rows, list):
                continue
            amount = Decimal("0")
            total_sum = Decimal("0")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("store") or "") != store_id:
                    continue
                if str(row.get("product") or "") != product_id:
                    continue
                amount += Decimal(str(row.get("amount") or "0"))
                total_sum += Decimal(str(row.get("sum") or "0"))
            if amount > 0:
                out.append(
                    BalanceRow(
                        store_id=store_id,
                        store_name=store_name,
                        product_id=product_id,
                        product_name=product_name,
                        amount=amount,
                        total_sum=total_sum,
                    )
                )
    return out


def _writeoff_one(
    client: httpx.Client,
    base_url: str,
    token: str,
    counteragent_id: str,
    row: BalanceRow,
) -> None:
    amount = row.amount
    if amount <= 0:
        return
    if row.total_sum > 0:
        price = row.total_sum / amount
    else:
        price = Decimal("0.01")
    sum_value = price * amount
    doc_number = f"bot-reset-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    date_incoming = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<document>
  <documentNumber>{doc_number}</documentNumber>
  <dateIncoming>{date_incoming}</dateIncoming>
  <useDefaultDocumentTime>true</useDefaultDocumentTime>
  <status>PROCESSED</status>
  <defaultStoreId>{row.store_id}</defaultStoreId>
  <counteragentId>{counteragent_id}</counteragentId>
  <items>
    <item>
      <productId>{row.product_id}</productId>
      <price>{price.normalize()}</price>
      <amount>{amount.normalize()}</amount>
      <sum>{sum_value.normalize()}</sum>
    </item>
  </items>
</document>"""
    resp = client.post(
        f"{base_url.rstrip('/')}/resto/api/documents/import/outgoingInvoice",
        params={"key": token},
        cookies={"key": token},
        headers={"content-type": "application/xml; charset=utf-8"},
        content=xml_payload.encode("utf-8"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Write-off failed: {resp.status_code} {resp.text[:300]}")


def main() -> int:
    args = _args()
    with httpx.Client(timeout=30, verify=args.verify_tls) as client:
        token = _auth(client, args.base_url, args.login, args.password)
        stores = _stores(client, args.base_url, token)
        products = _goods(client, args.base_url, token)
        nonzero = _balances(client, args.base_url, token, stores, products)
        print(f"Non-zero rows: {len(nonzero)}")
        for row in nonzero:
            print(
                f"- store={row.store_name} product={row.product_name} "
                f"amount={row.amount} sum={row.total_sum}"
            )

        if not args.apply:
            print("Dry-run mode. Use --apply to execute write-off.")
            return 0

        if nonzero:
            counteragent_id = _employee_id(client, args.base_url, token)
            for row in nonzero:
                _writeoff_one(client, args.base_url, token, counteragent_id, row)
            print("Write-off documents sent. Re-checking balances...")
            remaining = _balances(client, args.base_url, token, stores, products)
            print(f"Remaining non-zero rows: {len(remaining)}")
            if remaining:
                return 2
        else:
            print("Nothing to reset in balances.")

        if args.delete_products:
            current_products = _all_products(client, args.base_url, token)
            print(f"Deleting active products: {len(current_products)}")
            _delete_products(
                client,
                args.base_url,
                token,
                [product_id for product_id, _name in current_products],
            )
            after_delete = _all_products(client, args.base_url, token)
            print(f"Active products after delete: {len(after_delete)}")
            if after_delete:
                return 3
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
