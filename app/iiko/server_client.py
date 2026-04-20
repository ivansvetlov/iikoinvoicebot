"""HTTP client for iikoServer API (auth + incoming invoice import)."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx

from app.config import settings
from app.schemas import InvoiceItem


@dataclass(slots=True)
class _ProductRef:
    product_id: str
    name: str
    article: str = ""
    code: str = ""
    product_type: str = ""
    main_unit: str = ""
    accounting_category: str = ""


@dataclass(slots=True)
class _StoreRef:
    store_id: str
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class _BalanceTarget:
    product_id: str
    store_id: str
    expected_amount: Decimal


@dataclass(slots=True)
class IikoUploadResult:
    document_number: str
    requested_status: str
    valid: bool | None = None
    warning: bool | None = None
    document_id: str = ""
    exported_status: str = ""
    stock_verified: bool = False
    stock_warning: str = ""
    balance_deltas: list[dict[str, str]] = field(default_factory=list)


class IikoServerClient:
    """Uploads parsed invoice items to iiko using server-side API."""

    _catalog_cache: dict[str, tuple[float, list[_ProductRef]]] = {}
    _stores_cache: dict[str, tuple[float, list[_StoreRef]]] = {}

    async def verify_credentials(self, username: str, password: str) -> None:
        """Check iiko API auth with provided credentials."""
        if not settings.iiko_api_base_url.strip():
            raise RuntimeError("IIKO_API_BASE_URL is not configured")
        if not username or not password:
            raise RuntimeError("IIKO credentials are not configured")

        timeout = max(5, int(settings.iiko_api_timeout_sec or 30))
        verify_tls = bool(settings.iiko_api_verify_tls)
        auth_url = self._build_url(settings.iiko_api_base_url, settings.iiko_api_auth_path)

        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            token = await self._authenticate(client, auth_url, username, password)
            await self._logout(client, token)

    async def upload_invoice_items(
        self,
        items: list[InvoiceItem],
        username: str,
        password: str,
    ) -> IikoUploadResult:
        transport = (settings.iiko_transport or "import_only").strip().lower()
        if transport != "api":
            raise RuntimeError("IIKO transport is disabled (IIKO_TRANSPORT != api)")
        if not settings.iiko_api_base_url.strip():
            raise RuntimeError("IIKO_API_BASE_URL is not configured")
        if not username or not password:
            raise RuntimeError("IIKO credentials are not configured")

        timeout = max(5, int(settings.iiko_api_timeout_sec or 30))
        verify_tls = bool(settings.iiko_api_verify_tls)
        auth_url = self._build_url(settings.iiko_api_base_url, settings.iiko_api_auth_path)
        upload_url = self._build_url(settings.iiko_api_base_url, settings.iiko_api_upload_path)

        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            token = ""
            try:
                token = await self._authenticate(client, auth_url, username, password)
                resolved_items = await self._resolve_items_for_upload(
                    client=client,
                    token=token,
                    username=username,
                    items=items,
                )
                target_status = self._normalized_invoice_status()
                balance_targets: list[_BalanceTarget] = []
                balances_before: dict[_BalanceTarget, tuple[Decimal, Decimal]] = {}
                if target_status == "PROCESSED" and bool(settings.iiko_verify_stock_balance):
                    balance_targets = self._collect_balance_targets(resolved_items)
                    if balance_targets:
                        balances_before = await self._get_store_balances(
                            client=client,
                            token=token,
                            targets=balance_targets,
                        )

                payload = self._build_upload_xml(resolved_items, target_status=target_status)
                document_number = self._extract_document_number(payload)
                response = await client.post(
                    upload_url,
                    params={"key": token},
                    cookies={"key": token},
                    headers={"content-type": "application/xml; charset=utf-8"},
                    content=payload,
                )
                self._raise_for_api_error(response, prefix="IIKO import failed")
                result = self._validate_upload_response(
                    response,
                    requested_status=target_status,
                    fallback_document_number=document_number,
                )
                if bool(settings.iiko_verify_upload):
                    await self._verify_upload_result(
                        client=client,
                        token=token,
                        result=result,
                        balance_targets=balance_targets,
                        balances_before=balances_before,
                    )
                return result
            finally:
                if token:
                    await self._logout(client, token)

    async def _resolve_items_for_upload(
        self,
        client: httpx.AsyncClient,
        token: str,
        username: str,
        items: list[InvoiceItem],
    ) -> list[InvoiceItem]:
        if not items:
            return items
        if not bool(settings.iiko_autoresolve_products):
            return items

        unresolved = [
            (index, item, self._normalized_extras(item))
            for index, item in enumerate(items, start=1)
            if self._requires_product_mapping(self._normalized_extras(item))
        ]
        if not unresolved:
            return items

        cache_key = self._build_cache_key(username=username)
        products = await self._get_products(client=client, token=token, cache_key=cache_key)

        article_index: dict[str, list[_ProductRef]] = {}
        code_index: dict[str, list[_ProductRef]] = {}
        name_index: dict[str, list[_ProductRef]] = {}
        for product in products:
            article_key = self._norm_text(product.article)
            code_key = self._norm_text(product.code)
            name_key = self._norm_text(product.name)
            if article_key:
                article_index.setdefault(article_key, []).append(product)
            if code_key:
                code_index.setdefault(code_key, []).append(product)
            if name_key:
                name_index.setdefault(name_key, []).append(product)

        default_store_id = await self._get_default_store_id(client=client, token=token, cache_key=cache_key)
        resolved_by_row: dict[int, InvoiceItem] = {}

        for index, item, extras in unresolved:
            product = self._match_product(
                extras=extras,
                item_name=item.name,
                article_index=article_index,
                code_index=code_index,
                name_index=name_index,
            )
            if product is None:
                continue

            merged_extras = dict(item.extras or {})
            if not self._first_non_empty(extras, keys=("product", "productid", "productguid")):
                merged_extras["product"] = product.product_id
            if not self._first_non_empty(extras, keys=("productarticle", "article", "num")) and product.article:
                merged_extras["productArticle"] = product.article
            if not self._first_non_empty(extras, keys=("code",)) and product.code:
                merged_extras["code"] = product.code
            if product.product_type:
                merged_extras["iikoProductType"] = product.product_type
            if default_store_id and not self._first_non_empty(extras, keys=("store", "storeid", "storeguid")):
                merged_extras["store"] = default_store_id

            resolved_by_row[index] = item.model_copy(update={"extras": merged_extras})

        if bool(settings.iiko_autocreate_products):
            unresolved_after_match = [(idx, it, ex) for idx, it, ex in unresolved if idx not in resolved_by_row]
            if unresolved_after_match:
                create_template = self._pick_product_create_template(products)
                if create_template is None:
                    create_template = await self._get_create_template_from_deleted_catalog(client=client, token=token)
                created_by_name: dict[str, _ProductRef] = {}
                for index, item, extras in unresolved_after_match:
                    if not create_template:
                        break
                    norm_name = self._norm_text(item.name)
                    created = created_by_name.get(norm_name)
                    if created is None:
                        created = await self._create_product_for_item(
                            client=client,
                            token=token,
                            item=item,
                            row_index=index,
                            template=create_template,
                        )
                        created_by_name[norm_name] = created

                    merged_extras = dict(item.extras or {})
                    merged_extras["product"] = created.product_id
                    if created.article:
                        merged_extras.setdefault("productArticle", created.article)
                    if created.code:
                        merged_extras.setdefault("code", created.code)
                    merged_extras["iikoProductType"] = "GOODS"
                    if default_store_id and not self._first_non_empty(extras, keys=("store", "storeid", "storeguid")):
                        merged_extras["store"] = default_store_id
                    resolved_by_row[index] = item.model_copy(update={"extras": merged_extras})

        if not resolved_by_row:
            unresolved_rows = [f"{index}:{(item.name or '').strip()[:80]}" for index, item, _extras in unresolved]
            if unresolved_rows:
                preview = ", ".join(unresolved_rows[:8])
                if len(unresolved_rows) > 8:
                    preview += ", ..."
                raise RuntimeError(
                    "IIKO product mapping failed for rows: "
                    f"{preview}. Add product/article mapping in source document or iiko catalog."
                )
            return items

        updated: list[InvoiceItem] = []
        for index, item in enumerate(items, start=1):
            updated.append(resolved_by_row.get(index, item))

        unresolved_rows = [
            f"{index}:{(item.name or '').strip()[:80]}"
            for index, item, _extras in unresolved
            if index not in resolved_by_row
        ]
        if unresolved_rows:
            preview = ", ".join(unresolved_rows[:8])
            if len(unresolved_rows) > 8:
                preview += ", ..."
            raise RuntimeError(
                "IIKO product mapping failed for rows: "
                f"{preview}. Add product/article mapping in source document or iiko catalog."
            )
        return updated

    async def _get_products(self, client: httpx.AsyncClient, token: str, cache_key: str) -> list[_ProductRef]:
        cached = self._catalog_cache.get(cache_key)
        ttl = max(0, int(settings.iiko_catalog_cache_sec or 300))
        now = time.monotonic()
        if cached and ttl > 0 and (now - cached[0]) <= ttl:
            return cached[1]

        url = self._build_url(settings.iiko_api_base_url, "/resto/api/v2/entities/products/list")
        response = await client.get(
            url,
            params={"key": token, "includeDeleted": "false"},
            cookies={"key": token},
        )
        self._raise_for_api_error(response, prefix="IIKO products list failed")
        payload = self._safe_json(response)
        raw_products = self._extract_list_payload(payload)

        products: list[_ProductRef] = []
        for raw in raw_products:
            if not isinstance(raw, dict):
                continue
            if bool(raw.get("deleted")):
                continue
            product_id = str(raw.get("id") or "").strip()
            name = str(raw.get("name") or "").strip()
            article = str(raw.get("num") or "").strip()
            code = str(raw.get("code") or "").strip()
            product_type = str(raw.get("type") or "").strip().upper()
            main_unit = str(raw.get("mainUnit") or "").strip()
            accounting_category = str(raw.get("accountingCategory") or "").strip()
            if not product_id or not name:
                continue
            products.append(
                _ProductRef(
                    product_id=product_id,
                    name=name,
                    article=article,
                    code=code,
                    product_type=product_type,
                    main_unit=main_unit,
                    accounting_category=accounting_category,
                )
            )

        if ttl > 0:
            self._catalog_cache[cache_key] = (now, products)
        return products

    async def _get_default_store_id(self, client: httpx.AsyncClient, token: str, cache_key: str) -> str:
        if not bool(settings.iiko_autofill_store):
            return ""

        cached = self._stores_cache.get(cache_key)
        ttl = max(0, int(settings.iiko_catalog_cache_sec or 300))
        now = time.monotonic()
        if cached and ttl > 0 and (now - cached[0]) <= ttl:
            stores = cached[1]
            return stores[0].store_id if len(stores) == 1 else ""

        url = self._build_url(settings.iiko_api_base_url, "/resto/api/corporation/stores")
        response = await client.get(
            url,
            params={"key": token, "revisionFrom": "-1"},
            cookies={"key": token},
        )
        if response.status_code >= 400:
            return ""

        stores: list[_StoreRef] = []
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            root = None
        if root is not None:
            for node in root.findall(".//corporateItemDto"):
                store_id = (node.findtext("id") or "").strip()
                code = (node.findtext("code") or "").strip()
                name = (node.findtext("name") or "").strip()
                node_type = (node.findtext("type") or "").strip().upper()
                if not store_id:
                    continue
                if node_type and node_type != "STORE":
                    continue
                stores.append(_StoreRef(store_id=store_id, code=code, name=name))

        if ttl > 0:
            self._stores_cache[cache_key] = (now, stores)
        return stores[0].store_id if len(stores) == 1 else ""

    def _pick_product_create_template(self, products: list[_ProductRef]) -> _ProductRef | None:
        for product in products:
            if product.product_type == "GOODS" and product.main_unit:
                return product
        for product in products:
            if product.main_unit:
                return product
        return None

    async def _get_create_template_from_deleted_catalog(
        self,
        *,
        client: httpx.AsyncClient,
        token: str,
    ) -> _ProductRef | None:
        """Fallback template for product auto-create when active catalog is empty."""
        url = self._build_url(settings.iiko_api_base_url, "/resto/api/v2/entities/products/list")
        try:
            response = await client.get(
                url,
                params={"key": token, "includeDeleted": "true"},
                cookies={"key": token},
            )
        except Exception:
            return None
        if response.status_code >= 400:
            return None
        payload = self._safe_json(response)
        raw_products = self._extract_list_payload(payload)
        candidates: list[_ProductRef] = []
        for raw in raw_products:
            if not isinstance(raw, dict):
                continue
            main_unit = str(raw.get("mainUnit") or "").strip()
            if not main_unit:
                continue
            candidates.append(
                _ProductRef(
                    product_id=str(raw.get("id") or "").strip(),
                    name=str(raw.get("name") or "").strip(),
                    article=str(raw.get("num") or "").strip(),
                    code=str(raw.get("code") or "").strip(),
                    product_type=str(raw.get("type") or "").strip().upper(),
                    main_unit=main_unit,
                    accounting_category=str(raw.get("accountingCategory") or "").strip(),
                )
            )
        return self._pick_product_create_template(candidates)

    async def _create_product_for_item(
        self,
        *,
        client: httpx.AsyncClient,
        token: str,
        item: InvoiceItem,
        row_index: int,
        template: _ProductRef,
    ) -> _ProductRef:
        save_url = self._build_url(settings.iiko_api_base_url, "/resto/api/v2/entities/products/save")
        raw_name = (item.name or "").strip() or f"Item {row_index}"
        prefix = str(settings.iiko_autocreate_name_prefix or "").strip()
        product_name = f"{prefix} {raw_name}".strip()
        payload: dict[str, Any] = {
            "name": product_name[:200],
            "type": "GOODS",
            "mainUnit": template.main_unit,
            "useBalanceForSell": False,
            "defaultSalePrice": 0,
            "estimatedPurchasePrice": 0,
        }
        if template.accounting_category:
            payload["accountingCategory"] = template.accounting_category

        response = await client.post(
            save_url,
            params={"key": token},
            cookies={"key": token},
            json=payload,
        )
        self._raise_for_api_error(response, prefix="IIKO product create failed")
        body = self._safe_json(response)
        if not isinstance(body, dict):
            raise RuntimeError("IIKO product create failed: empty response")
        if str(body.get("result") or "").upper() not in {"", "SUCCESS"}:
            raise RuntimeError(f"IIKO product create failed: {body}")

        created = body.get("response")
        if not isinstance(created, dict):
            raise RuntimeError("IIKO product create failed: malformed response")
        product_id = str(created.get("id") or "").strip()
        if not product_id:
            raise RuntimeError("IIKO product create failed: missing product id")
        return _ProductRef(
            product_id=product_id,
            name=str(created.get("name") or product_name).strip(),
            article=str(created.get("num") or "").strip(),
            code=str(created.get("code") or "").strip(),
            product_type=str(created.get("type") or "GOODS").strip().upper(),
            main_unit=str(created.get("mainUnit") or template.main_unit).strip(),
            accounting_category=str(created.get("accountingCategory") or template.accounting_category).strip(),
        )

    def _match_product(
        self,
        extras: dict[str, str],
        item_name: str,
        article_index: dict[str, list[_ProductRef]],
        code_index: dict[str, list[_ProductRef]],
        name_index: dict[str, list[_ProductRef]],
    ) -> _ProductRef | None:
        for key in ("productarticle", "article", "num", "sku"):
            raw = extras.get(key)
            if not raw:
                continue
            candidates = article_index.get(self._norm_text(raw), [])
            choice = self._pick_best_candidate(candidates)
            if choice:
                return choice

        for key in ("code", "sku"):
            raw = extras.get(key)
            if not raw:
                continue
            candidates = code_index.get(self._norm_text(raw), [])
            choice = self._pick_best_candidate(candidates)
            if choice:
                return choice

        normalized_name = self._norm_text(item_name)
        if not normalized_name:
            return None

        exact = name_index.get(normalized_name, [])
        choice = self._pick_best_candidate(exact)
        if choice:
            return choice

        contains: list[_ProductRef] = []
        for ref in self._iter_unique_products(name_index):
            name_norm = self._norm_text(ref.name)
            if not name_norm:
                continue
            if normalized_name in name_norm or name_norm in normalized_name:
                contains.append(ref)
        return self._pick_best_candidate(contains)

    def _pick_best_candidate(self, candidates: list[_ProductRef]) -> _ProductRef | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        scored = sorted(candidates, key=self._candidate_score, reverse=True)
        if len(scored) >= 2 and self._candidate_score(scored[0]) == self._candidate_score(scored[1]):
            return None
        return scored[0]

    def _candidate_score(self, ref: _ProductRef) -> tuple[int, int]:
        type_rank = 0
        if ref.product_type in {"GOODS", "SEMI_FINISHED", "SEMIFINISHED", "INGREDIENT"}:
            type_rank = 3
        elif ref.product_type in {"DISH", "MODIFIER"}:
            type_rank = 2
        elif ref.product_type == "SERVICE":
            type_rank = 1
        has_article = 1 if ref.article else 0
        return type_rank, has_article

    def _iter_unique_products(self, name_index: dict[str, list[_ProductRef]]) -> list[_ProductRef]:
        seen: set[str] = set()
        unique: list[_ProductRef] = []
        for refs in name_index.values():
            for ref in refs:
                if ref.product_id in seen:
                    continue
                seen.add(ref.product_id)
                unique.append(ref)
        return unique

    def _build_cache_key(self, username: str) -> str:
        base = settings.iiko_api_base_url.strip().lower().rstrip("/")
        return f"{base}|{username.strip().lower()}"

    async def _authenticate(
        self,
        client: httpx.AsyncClient,
        auth_url: str,
        username: str,
        password: str,
    ) -> str:
        password_hash = hashlib.sha1(password.encode("utf-8")).hexdigest()
        auth_payload = {"login": username, "pass": password_hash}
        attempts = [
            ("form", lambda: client.post(auth_url, data=auth_payload)),
            ("query", lambda: client.post(auth_url, params=auth_payload)),
        ]
        last_error: str = "unknown auth error"

        for mode, request_call in attempts:
            response = await request_call()
            if response.status_code >= 400:
                body = (response.text or "").strip()
                if len(body) > 400:
                    body = f"{body[:400]}...<truncated>"
                last_error = f"mode={mode}; status={response.status_code}; body={body or '<empty>'}"
                continue

            token = self._extract_token(response)
            if token:
                return token
            last_error = f"mode={mode}; status={response.status_code}; empty token"

        raise RuntimeError(f"IIKO auth failed: {last_error}")

    async def _logout(self, client: httpx.AsyncClient, token: str) -> None:
        if not token:
            return
        logout_url = self._build_url(settings.iiko_api_base_url, "/resto/api/logout")
        try:
            await client.post(
                logout_url,
                params={"key": token},
                cookies={"key": token},
            )
        except Exception:
            # Logout is best-effort. We should not fail business flow if token is already invalid.
            return

    def _extract_token(self, response: httpx.Response) -> str:
        # Prefer explicit cookie, then fallback to body token string.
        cookie_token = response.cookies.get("key")
        if cookie_token and cookie_token.strip():
            return cookie_token.strip()

        body = response.text.strip().strip('"').strip("'")
        if not body:
            return ""
        if body.startswith("<"):
            return ""
        if body.lower().startswith(("error", "exception")):
            return ""
        return body

    def _build_upload_xml(self, items: list[InvoiceItem], target_status: str | None = None) -> bytes:
        if not items:
            raise RuntimeError("IIKO import requires at least one item")

        root = ET.Element("document")
        items_el = ET.SubElement(root, "items")
        missing_rows: list[str] = []
        stores_used: set[str] = set()

        for index, item in enumerate(items, start=1):
            extras = self._normalized_extras(item)
            product = self._first_non_empty(
                extras,
                keys=("product", "productid", "productguid", "nomenclatureid", "nomenclatureguid"),
            )
            product_article = self._first_non_empty(extras, keys=("productarticle", "article", "num"))
            supplier_product = self._first_non_empty(
                extras,
                keys=("supplierproduct", "supplierproductid", "supplierproductguid"),
            )
            supplier_product_article = self._first_non_empty(
                extras,
                keys=("supplierproductarticle",),
            )
            if not any((product, product_article, supplier_product, supplier_product_article)):
                missing_rows.append(f"{index}:{(item.name or '').strip()[:80]}")
                continue

            item_el = ET.SubElement(items_el, "item")
            ET.SubElement(item_el, "num").text = str(index)
            if product:
                ET.SubElement(item_el, "product").text = product
            if product_article:
                ET.SubElement(item_el, "productArticle").text = product_article
            if supplier_product:
                ET.SubElement(item_el, "supplierProduct").text = supplier_product
            if supplier_product_article:
                ET.SubElement(item_el, "supplierProductArticle").text = supplier_product_article

            self._set_decimal(item_el, "amount", item.unit_amount or item.supply_quantity)
            self._set_decimal(item_el, "actualAmount", item.supply_quantity or item.unit_amount)
            self._set_decimal(item_el, "price", item.unit_price)
            self._set_decimal(item_el, "sumWithoutNds", item.cost_without_tax)
            self._set_decimal(item_el, "vatPercent", item.tax_rate)
            self._set_decimal(item_el, "vatSum", item.tax_amount)
            self._set_decimal(
                item_el,
                "sum",
                item.cost_with_tax or item.total_cost or item.cost_without_tax,
            )

            code = self._first_non_empty(extras, keys=("code", "sku"))
            store = self._first_non_empty(extras, keys=("store", "storeid", "storeguid"))
            if code:
                ET.SubElement(item_el, "code").text = code
            if store:
                ET.SubElement(item_el, "store").text = store
                stores_used.add(store)

        if missing_rows:
            preview = ", ".join(missing_rows[:8])
            if len(missing_rows) > 8:
                preview += ", ..."
            raise RuntimeError(
                "IIKO item mapping is missing product identifiers "
                "(product/productArticle/supplierProduct/supplierProductArticle) for rows: "
                f"{preview}"
            )

        if len(items_el) == 0:
            raise RuntimeError("IIKO import payload has no usable items")
        self._append_document_metadata(
            root=root,
            stores_used=stores_used,
            target_status=target_status,
            supplier_id=self._extract_document_supplier_id(items),
        )
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _append_document_metadata(
        self,
        root: ET.Element,
        stores_used: set[str],
        target_status: str | None,
        supplier_id: str,
    ) -> None:
        # Demo and many production stands throw NPE for incomingInvoice without minimal document meta.
        doc_number = f"bot-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        ET.SubElement(root, "documentNumber").text = doc_number
        ET.SubElement(root, "incomingDocumentNumber").text = doc_number
        ET.SubElement(root, "dateIncoming").text = datetime.now().strftime("%d.%m.%Y")
        ET.SubElement(root, "useDefaultDocumentTime").text = "true"
        if target_status:
            ET.SubElement(root, "status").text = target_status
        if supplier_id:
            ET.SubElement(root, "supplier").text = supplier_id
        if len(stores_used) == 1:
            ET.SubElement(root, "defaultStore").text = next(iter(stores_used))

    def _extract_document_supplier_id(self, items: list[InvoiceItem]) -> str:
        explicit: set[str] = set()
        for item in items:
            value = self._first_non_empty(
                self._normalized_extras(item),
                keys=("supplier", "supplierid", "supplierguid", "vendor", "vendorid", "vendorguid"),
            )
            if value:
                explicit.add(value)
        if len(explicit) > 1:
            raise RuntimeError("IIKO import requires one supplier per incoming invoice")
        if explicit:
            return next(iter(explicit))
        return (settings.iiko_default_supplier_id or "").strip()

    def _normalized_invoice_status(self) -> str:
        value = (settings.iiko_incoming_invoice_status or "").strip().upper()
        if not value:
            return ""
        if value not in {"NEW", "PROCESSED"}:
            raise RuntimeError("IIKO_INCOMING_INVOICE_STATUS must be NEW or PROCESSED")
        return value

    def _set_decimal(self, parent: ET.Element, field_name: str, value: Decimal | None) -> None:
        if value is None:
            return
        ET.SubElement(parent, field_name).text = self._decimal_to_text(value)

    def _decimal_to_text(self, value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        if text in {"", "-0"}:
            text = "0"
        return text

    def _normalized_extras(self, item: InvoiceItem) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in (item.extras or {}).items():
            key = re.sub(r"[^a-z0-9]+", "", str(raw_key).strip().lower())
            value = str(raw_value).strip()
            if key and value:
                normalized[key] = value
        return normalized

    def _requires_product_mapping(self, extras: dict[str, str]) -> bool:
        return not bool(
            self._first_non_empty(
                extras,
                keys=(
                    "product",
                    "productid",
                    "productguid",
                    "productarticle",
                    "article",
                    "num",
                    "supplierproduct",
                    "supplierproductid",
                    "supplierproductguid",
                    "supplierproductarticle",
                ),
            )
        )

    def _first_non_empty(self, data: dict[str, str], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = data.get(key)
            if value:
                return value
        return ""

    def _norm_text(self, value: str) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
        normalized = re.sub(r"[^\w\s\-./]", "", normalized)
        return normalized.strip()

    def _safe_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return None

    def _extract_list_payload(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("response"), list):
                return payload["response"]
            if isinstance(payload.get("items"), list):
                return payload["items"]
        return []

    def _validate_upload_response(
        self,
        response: httpx.Response,
        requested_status: str,
        fallback_document_number: str,
    ) -> IikoUploadResult:
        result = IikoUploadResult(
            document_number=fallback_document_number,
            requested_status=requested_status,
        )
        payload = response.text.strip()
        if not payload or not payload.startswith("<"):
            return result
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return result

        tag = root.tag.lower()
        if tag.endswith("documentvalidationresult"):
            valid = (root.findtext("valid") or "").strip().lower()
            warning = (root.findtext("warning") or "").strip().lower()
            result.valid = valid == "true" if valid in {"true", "false"} else None
            result.warning = warning == "true" if warning in {"true", "false"} else None
            result.document_number = (root.findtext("documentNumber") or fallback_document_number).strip()
            if valid == "false":
                raise RuntimeError(f"IIKO import validation failed: {payload[:300]}")
        return result

    async def _verify_upload_result(
        self,
        client: httpx.AsyncClient,
        token: str,
        result: IikoUploadResult,
        balance_targets: list[_BalanceTarget],
        balances_before: dict[_BalanceTarget, tuple[Decimal, Decimal]],
    ) -> None:
        if not result.document_number:
            raise RuntimeError("IIKO import did not return document number")

        verify_attempts = max(1, int(settings.iiko_verify_attempts or 1))
        verify_delay = max(0.0, float(settings.iiko_verify_delay_sec or 0.0))

        document: ET.Element | None = None
        for attempt in range(verify_attempts):
            document = await self._export_invoice_by_number(
                client=client,
                token=token,
                document_number=result.document_number,
            )
            if document is not None:
                break
            if attempt < verify_attempts - 1 and verify_delay > 0:
                await asyncio.sleep(verify_delay)
        if document is None:
            raise RuntimeError(f"IIKO import verification failed: document not found: {result.document_number}")

        result.document_id = (document.findtext("id") or "").strip()
        result.exported_status = (document.findtext("status") or "").strip().upper()
        if result.requested_status and result.exported_status != result.requested_status:
            raise RuntimeError(
                "IIKO import verification failed: "
                f"expected status {result.requested_status}, got {result.exported_status or '<empty>'}"
            )

        if result.requested_status != "PROCESSED" or not balance_targets:
            if result.requested_status == "PROCESSED":
                result.stock_warning = "stock balance verification skipped: no product/store targets"
            return

        failures: list[str] = []
        for attempt in range(verify_attempts):
            balances_after = await self._get_store_balances(client=client, token=token, targets=balance_targets)
            failures = []
            deltas: list[dict[str, str]] = []
            for target in balance_targets:
                before_amount, before_sum = balances_before.get(target, (Decimal("0"), Decimal("0")))
                after_amount, after_sum = balances_after.get(target, (Decimal("0"), Decimal("0")))
                amount_delta = after_amount - before_amount
                sum_delta = after_sum - before_sum
                deltas.append(
                    {
                        "product": target.product_id,
                        "store": target.store_id,
                        "amount_delta": self._decimal_to_text(amount_delta),
                        "sum_delta": self._decimal_to_text(sum_delta),
                    }
                )
                if amount_delta < target.expected_amount:
                    failures.append(
                        f"{target.product_id}@{target.store_id}: "
                        f"expected +{self._decimal_to_text(target.expected_amount)}, "
                        f"got +{self._decimal_to_text(amount_delta)}"
                    )
            result.balance_deltas = deltas
            if not failures:
                break
            if attempt < verify_attempts - 1 and verify_delay > 0:
                await asyncio.sleep(verify_delay)
        if failures:
            preview = "; ".join(failures[:5])
            result.stock_warning = f"stock verification warning: {preview}"
            result.stock_verified = False
            return
        result.stock_verified = True

    async def _export_invoice_by_number(
        self,
        client: httpx.AsyncClient,
        token: str,
        document_number: str,
    ) -> ET.Element | None:
        url = self._build_url(settings.iiko_api_base_url, "/resto/api/documents/export/incomingInvoice/byNumber")
        response = await client.get(
            url,
            params={"key": token, "number": document_number, "currentYear": "true"},
            cookies={"key": token},
        )
        self._raise_for_api_error(response, prefix="IIKO import verification export failed")
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise RuntimeError("IIKO import verification export returned invalid XML") from exc

        documents = root.findall(".//document") if root.tag != "document" else [root]
        for document in documents:
            if (document.findtext("documentNumber") or "").strip() == document_number:
                return document
        return documents[0] if documents else None

    def _collect_balance_targets(self, items: list[InvoiceItem]) -> list[_BalanceTarget]:
        grouped: dict[tuple[str, str], Decimal] = {}
        for item in items:
            extras = self._normalized_extras(item)
            product_type = self._first_non_empty(extras, keys=("iikoproducttype", "producttype")).upper()
            if product_type == "SERVICE":
                continue
            product = self._first_non_empty(
                extras,
                keys=("product", "productid", "productguid", "nomenclatureid", "nomenclatureguid"),
            )
            store = self._first_non_empty(extras, keys=("store", "storeid", "storeguid"))
            amount = item.supply_quantity or item.unit_amount
            if not product or not store or amount is None:
                continue
            grouped[(product, store)] = grouped.get((product, store), Decimal("0")) + amount
        return [
            _BalanceTarget(product_id=product, store_id=store, expected_amount=amount)
            for (product, store), amount in grouped.items()
            if amount > 0
        ]

    async def _get_store_balances(
        self,
        client: httpx.AsyncClient,
        token: str,
        targets: list[_BalanceTarget],
    ) -> dict[_BalanceTarget, tuple[Decimal, Decimal]]:
        url = self._build_url(settings.iiko_api_base_url, "/resto/api/v2/reports/balance/stores")
        balances: dict[_BalanceTarget, tuple[Decimal, Decimal]] = {}
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        for target in targets:
            response = await client.get(
                url,
                params={
                    "key": token,
                    "timestamp": timestamp,
                    "store": target.store_id,
                    "product": target.product_id,
                },
                cookies={"key": token},
            )
            self._raise_for_api_error(response, prefix="IIKO stock balance verification failed")
            payload = self._safe_json(response)
            rows = payload if isinstance(payload, list) else []
            amount = Decimal("0")
            total_sum = Decimal("0")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("store") or "") != target.store_id:
                    continue
                if str(row.get("product") or "") != target.product_id:
                    continue
                amount += self._decimal_from_api(row.get("amount"))
                total_sum += self._decimal_from_api(row.get("sum"))
            balances[target] = (amount, total_sum)
        return balances

    def _extract_document_number(self, payload: bytes) -> str:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return ""
        return (root.findtext("documentNumber") or "").strip()

    def _decimal_from_api(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def _raise_for_api_error(self, response: httpx.Response, prefix: str) -> None:
        if response.status_code < 400:
            return
        body = (response.text or "").strip()
        if len(body) > 700:
            body = f"{body[:700]}...<truncated>"
        raise RuntimeError(f"{prefix}: status={response.status_code}; body={body or '<empty>'}")

    def _build_url(self, base: str, path: str) -> str:
        clean_base = base.rstrip("/")
        clean_path = "/" + path.lstrip("/")
        return f"{clean_base}{clean_path}"
