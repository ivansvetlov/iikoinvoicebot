from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx

from app.iiko.server_client import IikoServerClient, _ProductRef
from app.schemas import InvoiceItem


class IikoServerClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = IikoServerClient()

    def test_extract_token_prefers_cookie(self) -> None:
        response = httpx.Response(
            200,
            text="body-token",
            headers={"set-cookie": "key=cookie-token; Path=/; HttpOnly"},
            request=httpx.Request("POST", "https://example.local/auth"),
        )
        self.assertEqual(self.client._extract_token(response), "cookie-token")

    def test_extract_token_fallbacks_to_body(self) -> None:
        response = httpx.Response(
            200,
            text="plain-token",
            request=httpx.Request("POST", "https://example.local/auth"),
        )
        self.assertEqual(self.client._extract_token(response), "plain-token")

    def test_build_upload_xml_requires_product_mapping(self) -> None:
        items = [
            InvoiceItem(
                name="Milk",
                unit_amount=Decimal("3"),
                unit_price=Decimal("10"),
                cost_without_tax=Decimal("30"),
            )
        ]
        with self.assertRaises(RuntimeError) as ctx:
            self.client._build_upload_xml(items)
        self.assertIn("missing product identifiers", str(ctx.exception))

    def test_build_upload_xml_accepts_product_article(self) -> None:
        items = [
            InvoiceItem(
                name="Milk",
                unit_amount=Decimal("1"),
                unit_price=Decimal("10"),
                cost_without_tax=Decimal("10"),
                cost_with_tax=Decimal("10"),
                extras={"productArticle": "00001"},
            )
        ]
        xml_bytes = self.client._build_upload_xml(items)
        root = ET.fromstring(xml_bytes)
        item = root.find("./items/item")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.findtext("productArticle"), "00001")
        self.assertEqual(item.findtext("sum"), "10")

    def test_build_upload_xml_contains_required_fields(self) -> None:
        items = [
            InvoiceItem(
                name="Milk",
                unit_amount=Decimal("3.00"),
                unit_price=Decimal("10.00"),
                cost_without_tax=Decimal("30.00"),
                tax_rate=Decimal("20"),
                tax_amount=Decimal("6"),
                cost_with_tax=Decimal("36"),
                extras={"product": "P1", "store": "S1", "code": "A-001"},
            )
        ]
        xml_bytes = self.client._build_upload_xml(items)
        root = ET.fromstring(xml_bytes)

        self.assertEqual(root.tag, "document")
        item = root.find("./items/item")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.findtext("product"), "P1")
        self.assertEqual(item.findtext("num"), "1")
        self.assertEqual(item.findtext("amount"), "3")
        self.assertEqual(item.findtext("price"), "10")
        self.assertEqual(item.findtext("sumWithoutNds"), "30")
        self.assertEqual(item.findtext("vatPercent"), "20")
        self.assertEqual(item.findtext("vatSum"), "6")
        self.assertEqual(item.findtext("sum"), "36")
        self.assertEqual(item.findtext("store"), "S1")
        self.assertEqual(item.findtext("code"), "A-001")
        self.assertTrue(root.findtext("documentNumber"))
        self.assertTrue(root.findtext("incomingDocumentNumber"))
        self.assertTrue(root.findtext("dateIncoming"))
        self.assertEqual(root.findtext("useDefaultDocumentTime"), "true")
        self.assertEqual(root.findtext("defaultStore"), "S1")

    def test_build_upload_xml_can_request_processed_with_supplier(self) -> None:
        items = [
            InvoiceItem(
                name="Milk",
                unit_amount=Decimal("2"),
                unit_price=Decimal("10"),
                cost_without_tax=Decimal("20"),
                cost_with_tax=Decimal("20"),
                extras={"product": "P1", "store": "S1", "supplier": "SUP1"},
            )
        ]
        xml_bytes = self.client._build_upload_xml(items, target_status="PROCESSED")
        root = ET.fromstring(xml_bytes)
        self.assertEqual(root.findtext("status"), "PROCESSED")
        self.assertEqual(root.findtext("supplier"), "SUP1")

    def test_validate_upload_response_returns_document_number(self) -> None:
        response = httpx.Response(
            200,
            text=(
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<documentValidationResult>"
                "<valid>true</valid>"
                "<warning>false</warning>"
                "<documentNumber>dn-1</documentNumber>"
                "</documentValidationResult>"
            ),
            request=httpx.Request("POST", "https://example.local/import"),
        )
        result = self.client._validate_upload_response(
            response,
            requested_status="NEW",
            fallback_document_number="fallback",
        )
        self.assertEqual(result.document_number, "dn-1")
        self.assertEqual(result.requested_status, "NEW")
        self.assertTrue(result.valid)
        self.assertFalse(result.warning)

    def test_collect_balance_targets_groups_goods_and_skips_services(self) -> None:
        items = [
            InvoiceItem(
                name="Milk",
                unit_amount=Decimal("2"),
                extras={"product": "P1", "store": "S1", "iikoProductType": "GOODS"},
            ),
            InvoiceItem(
                name="Milk extra",
                supply_quantity=Decimal("3"),
                extras={"product": "P1", "store": "S1", "iikoProductType": "GOODS"},
            ),
            InvoiceItem(
                name="Delivery",
                unit_amount=Decimal("1"),
                extras={"product": "P2", "store": "S1", "iikoProductType": "SERVICE"},
            ),
        ]
        targets = self.client._collect_balance_targets(items)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].product_id, "P1")
        self.assertEqual(targets[0].store_id, "S1")
        self.assertEqual(targets[0].expected_amount, Decimal("5"))


class IikoServerClientAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = IikoServerClient()

    async def test_verify_credentials_calls_authenticate_and_logout(self) -> None:
        with patch("app.iiko.server_client.settings.iiko_api_base_url", "https://demo.iiko.it/resto"):
            with patch.object(self.client, "_authenticate", new=AsyncMock(return_value="token")) as auth:
                with patch.object(self.client, "_logout", new=AsyncMock(return_value=None)) as logout:
                    await self.client.verify_credentials("user", "pass")
        self.assertEqual(auth.await_count, 1)
        self.assertEqual(logout.await_count, 1)

    async def test_verify_credentials_requires_base_url(self) -> None:
        with patch("app.iiko.server_client.settings.iiko_api_base_url", ""):
            with self.assertRaises(RuntimeError) as ctx:
                await self.client.verify_credentials("user", "pass")
        self.assertIn("IIKO_API_BASE_URL is not configured", str(ctx.exception))

    async def test_upload_logs_out_even_when_processing_fails(self) -> None:
        items = [InvoiceItem(name="Milk", unit_amount=Decimal("1"), extras={"productArticle": "00001"})]
        with patch("app.iiko.server_client.settings.iiko_transport", "api"):
            with patch("app.iiko.server_client.settings.iiko_api_base_url", "https://demo.iiko.it/resto"):
                with patch.object(self.client, "_authenticate", new=AsyncMock(return_value="token")):
                    with patch.object(
                        self.client,
                        "_resolve_items_for_upload",
                        new=AsyncMock(side_effect=RuntimeError("resolve failed")),
                    ):
                        with patch.object(self.client, "_logout", new=AsyncMock(return_value=None)) as logout:
                            with self.assertRaises(RuntimeError) as ctx:
                                await self.client.upload_invoice_items(items, "user", "pass")
        self.assertIn("resolve failed", str(ctx.exception))
        self.assertEqual(logout.await_count, 1)


class IikoServerClientResolveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = IikoServerClient()

    async def test_resolve_items_for_upload_fills_product_and_store(self) -> None:
        items = [InvoiceItem(name="Молоко 1л", extras={})]
        products = [
            _ProductRef(
                product_id="P1",
                name="Молоко 1л",
                article="00001",
                code="101",
                product_type="GOODS",
            )
        ]

        with patch("app.iiko.server_client.settings.iiko_autoresolve_products", True):
            with patch("app.iiko.server_client.settings.iiko_autofill_store", True):
                with patch.object(self.client, "_get_products", new=AsyncMock(return_value=products)):
                    with patch.object(self.client, "_get_default_store_id", new=AsyncMock(return_value="S1")):
                        async with httpx.AsyncClient() as http_client:
                            resolved = await self.client._resolve_items_for_upload(
                                client=http_client,
                                token="token",
                                username="user",
                                items=items,
                            )

        self.assertEqual(len(resolved), 1)
        extras = resolved[0].extras
        self.assertEqual(extras.get("product"), "P1")
        self.assertEqual(extras.get("productArticle"), "00001")
        self.assertEqual(extras.get("code"), "101")
        self.assertEqual(extras.get("store"), "S1")

    async def test_resolve_items_for_upload_raises_when_partial_mapping(self) -> None:
        items = [
            InvoiceItem(name="Молоко 1л", extras={}),
            InvoiceItem(name="Неизвестный товар", extras={}),
        ]
        products = [
            _ProductRef(
                product_id="P1",
                name="Молоко 1л",
                article="00001",
                code="101",
                product_type="GOODS",
            )
        ]

        with patch("app.iiko.server_client.settings.iiko_autoresolve_products", True):
            with patch("app.iiko.server_client.settings.iiko_autofill_store", False):
                with patch.object(self.client, "_get_products", new=AsyncMock(return_value=products)):
                    with patch.object(self.client, "_get_default_store_id", new=AsyncMock(return_value="")):
                        async with httpx.AsyncClient() as http_client:
                            with self.assertRaises(RuntimeError) as ctx:
                                await self.client._resolve_items_for_upload(
                                    client=http_client,
                                    token="token",
                                    username="user",
                                    items=items,
                                )

        self.assertIn("IIKO product mapping failed for rows", str(ctx.exception))

    async def test_resolve_items_for_upload_autocreates_missing_products(self) -> None:
        items = [InvoiceItem(name="Новый товар", extras={})]
        products = [
            _ProductRef(
                product_id="TPL1",
                name="Шаблон товара",
                article="001",
                code="C001",
                product_type="GOODS",
                main_unit="UNIT1",
                accounting_category="ACC1",
            )
        ]
        created = _ProductRef(
            product_id="NEW1",
            name="Новый товар",
            article="00077",
            code="A777",
            product_type="GOODS",
            main_unit="UNIT1",
            accounting_category="ACC1",
        )

        with patch("app.iiko.server_client.settings.iiko_autoresolve_products", True):
            with patch("app.iiko.server_client.settings.iiko_autocreate_products", True):
                with patch("app.iiko.server_client.settings.iiko_autofill_store", True):
                    with patch.object(self.client, "_get_products", new=AsyncMock(return_value=products)):
                        with patch.object(self.client, "_get_default_store_id", new=AsyncMock(return_value="S1")):
                            with patch.object(
                                self.client,
                                "_create_product_for_item",
                                new=AsyncMock(return_value=created),
                            ) as create_mock:
                                async with httpx.AsyncClient() as http_client:
                                    resolved = await self.client._resolve_items_for_upload(
                                        client=http_client,
                                        token="token",
                                        username="user",
                                        items=items,
                                    )
        self.assertEqual(create_mock.await_count, 1)
        extras = resolved[0].extras
        self.assertEqual(extras.get("product"), "NEW1")
        self.assertEqual(extras.get("productArticle"), "00077")
        self.assertEqual(extras.get("code"), "A777")
        self.assertEqual(extras.get("store"), "S1")

    async def test_resolve_items_for_upload_raises_when_autocreate_without_template(self) -> None:
        items = [InvoiceItem(name="Новый товар", extras={})]
        with patch("app.iiko.server_client.settings.iiko_autoresolve_products", True):
            with patch("app.iiko.server_client.settings.iiko_autocreate_products", True):
                with patch("app.iiko.server_client.settings.iiko_autofill_store", False):
                    with patch.object(self.client, "_get_products", new=AsyncMock(return_value=[])):
                        with patch.object(self.client, "_get_default_store_id", new=AsyncMock(return_value="")):
                            async with httpx.AsyncClient() as http_client:
                                with self.assertRaises(RuntimeError) as ctx:
                                    await self.client._resolve_items_for_upload(
                                        client=http_client,
                                        token="token",
                                        username="user",
                                        items=items,
                                    )
        self.assertIn("IIKO product mapping failed for rows", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
