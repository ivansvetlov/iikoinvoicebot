"""
E2E Тесты: Загрузка и оприходование накладной
Реализация фреймворка для полного цикла тестирования
"""
from __future__ import annotations

import unittest

try:
    import pytest
except ImportError as exc:
    raise unittest.SkipTest("pytest required for e2e invoice posting tests") from exc
import time
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# pytest fixtures для E2E тестов
@pytest.fixture
def iiko_web_helper():
    """Помощник для взаимодействия с iiko Web UI"""
    from tests.e2e.helpers.iiko_web_helper import IikoWebHelper
    return IikoWebHelper(
        base_url="https://840-786-070.iikoweb.ru",
        crmid="8950663"
    )

@pytest.fixture
def bot_client():
    """Клиент для взаимодействия с Telegram ботом"""
    from tests.e2e.helpers.telegram_client import TelegramBotClient
    return TelegramBotClient(
        bot_token="DEV_BOT_TOKEN",  # из .env
        user_id="DEV_USER_ID"        # из .env
    )

@pytest.fixture
def invoice_generator():
    """Генератор тестовых накладных"""
    from tests.e2e.helpers.invoice_generator import InvoiceGenerator
    return InvoiceGenerator(output_dir="tests/e2e/fixtures/generated")

@pytest.fixture
def e2e_assertions():
    """Кастомные проверки для E2E"""
    from tests.e2e.helpers.assertions import E2ETestAssertions
    return E2ETestAssertions()

# Основные E2E тесты

class TestInvoiceE2ESimplePath:
    """Тесты базового пути: Накладная → Парсинг → Маппинг → iiko → Баланс"""

    def test_01_simple_invoice_full_cycle(self, bot_client, iiko_web_helper, e2e_assertions):
        """
        Сценарий 1: Простая накладная (5 товаров, все в штуках)
        Ожидаемый результат: Товары оприходованы, баланс изменился
        """
        # Setup
        invoice_data = {
            "date": "2026-04-21",
            "supplier": "Тестовый поставщик",
            "items": [
                {"name": "Молоко 3.2%", "qty": 10, "unit": "шт", "price": 120},
                {"name": "Сливки 35%", "qty": 5, "unit": "шт", "price": 250},
                {"name": "Йогурт", "qty": 8, "unit": "шт", "price": 80},
                {"name": "Масло", "qty": 3, "unit": "шт", "price": 500},
                {"name": "Творог", "qty": 4, "unit": "шт", "price": 200},
            ]
        }

        # Act
        print("\n[E2E-01] Шаг 1: Отправляем накладную боту")
        invoice_bytes = invoice_generator.create_pdf_invoice(**invoice_data)
        response = bot_client.send_document(invoice_bytes)
        request_code = extract_request_code(response)
        print(f"Код заявки: {request_code}")

        print("[E2E-01] Шаг 2: Ждем обработки в воркере (max 30 сек)")
        result = wait_for_processing(bot_client, request_code, timeout=30)
        print(f"Статус: {result['status']}")

        print("[E2E-01] Шаг 3: Проверяем результаты парсинга")
        e2e_assertions.assert_invoice_recognized(result)
        e2e_assertions.assert_items_count(result, 5)

        print("[E2E-01] Шаг 4: Проверяем маппинг товаров")
        for item in result["items"]:
            assert item["name"], "Название товара должно быть"
            assert item["qty"] > 0, "Количество должно быть > 0"
            assert item.get("iiko_product_id"), "Товар должен быть замаплен или создан"

        print("[E2E-01] Шаг 5: Проверяем в iiko Web что товары оприходованы")
        iiko_document_number = result.get("iiko_document_number")
        assert iiko_document_number, "Должен быть номер документа в iiko"

        stock_items = iiko_web_helper.get_stock_by_document(iiko_document_number)
        e2e_assertions.assert_items_count({"items": stock_items}, 5)

        total_qty = sum(item["quantity"] for item in stock_items)
        expected_qty = sum(inv["qty"] for inv in invoice_data["items"])
        assert total_qty == expected_qty, f"Всего в stock: {total_qty}, ожидается: {expected_qty}"

        print(f"\n✅ [E2E-01] Тест пройден! Оприходовано {total_qty} товаров")

    def test_02_invoice_with_existing_products(self, bot_client, iiko_web_helper, e2e_assertions):
        """
        Сценарий 2: Накладная содержит товары, которые уже есть в iiko
        """
        print("\n[E2E-02] Поиск существующего товара в iiko...")

        # Setup: Получаем существующий товар
        existing_products = iiko_web_helper.get_all_products()
        if not existing_products:
            pytest.skip("Нет товаров в iiko для теста существующего продукта")

        existing_product = existing_products[0]
        product_name = existing_product["name"]
        product_id = existing_product["id"]
        print(f"Используем товар: {product_name} (ID: {product_id})")

        # Setup: Берем начальный баланс
        initial_stock = iiko_web_helper.get_stock_by_product_id(product_id)
        initial_qty = initial_stock.get("quantity", 0) if initial_stock else 0
        print(f"Начальный баланс: {initial_qty}")

        # Act: Отправляем накладную с существующим товаром
        print("\n[E2E-02] Отправляем накладную с существующим товаром")
        invoice_data = {
            "items": [
                {"name": product_name, "qty": 15, "unit": "шт", "price": 100},
            ]
        }
        invoice_bytes = invoice_generator.create_pdf_invoice(**invoice_data)
        response = bot_client.send_document(invoice_bytes)
        request_code = extract_request_code(response)

        print("[E2E-02] Ждем обработки...")
        result = wait_for_processing(bot_client, request_code, timeout=30)

        # Assert: Проверяем маппинг
        print("[E2E-02] Проверяем маппинг товара")
        assert len(result["items"]) == 1
        mapped_item = result["items"][0]
        assert mapped_item["iiko_product_id"] == product_id, \
            f"Товар должен быть замаплен как ID {product_id}"
        assert mapped_item["mapping_method"] in ["name_match", "article_match"], \
            "Маппинг должен быть по имени или артикулу"

        # Assert: Проверяем что баланс изменился
        print("[E2E-02] Проверяем что баланс изменился в iiko")
        iiko_document = result.get("iiko_document_number")
        new_stock = iiko_web_helper.get_stock_by_product_id(product_id)
        new_qty = new_stock.get("quantity", 0) if new_stock else initial_qty

        assert new_qty == initial_qty + 15, \
            f"Баланс должен быть {initial_qty + 15}, получено {new_qty}"

        print(f"\n✅ [E2E-02] Тест пройден! Баланс изменился: {initial_qty} → {new_qty}")

    def test_03_invoice_creates_new_products(self, bot_client, iiko_web_helper, e2e_assertions):
        """
        Сценарий 3: Создание новых товаров в iiko
        """
        print("\n[E2E-03] Создание новых товаров")

        # Setup: Генерируем уникальные названия
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        new_products = [
            {"name": f"TEST_New_Product_1_{timestamp}", "qty": 10, "unit": "шт", "price": 100},
            {"name": f"TEST_New_Product_2_{timestamp}", "qty": 5, "unit": "шт", "price": 200},
        ]

        print(f"[E2E-03] Новые товары: {[p['name'] for p in new_products]}")

        # Act: Отправляем накладную с новыми товарами
        invoice_data = {"items": new_products}
        invoice_bytes = invoice_generator.create_pdf_invoice(**invoice_data)
        response = bot_client.send_document(invoice_bytes)
        request_code = extract_request_code(response)

        print("[E2E-03] Ждем создания товаров в iiko...")
        result = wait_for_processing(bot_client, request_code, timeout=60)

        # Assert: Товары созданы
        print("[E2E-03] Проверяем что товары созданы")
        assert len(result["new_products"]) == 2, "Должны быть созданы 2 новых товара"

        for i, new_product_info in enumerate(result["new_products"]):
            created_product = iiko_web_helper.get_product(new_products[i]["name"])
            assert created_product is not None, f"Товар {new_products[i]['name']} не найден"
            assert created_product["active"] == True, "Товар должен быть активным"
            print(f"✓ Товар {i+1} создан: {created_product['name']} (ID: {created_product['id']})")

        print(f"\n✅ [E2E-03] Тест пройден! Созданы {len(result['new_products'])} новых товаров")

# Вспомогательные функции

def extract_request_code(response: str) -> str:
    """Извлекает код заявки из ответа бота"""
    import re
    match = re.search(r'Код заявки:\s+(\d+)', response)
    if match:
        return match.group(1)
    raise ValueError(f"Не найден код заявки в ответе: {response}")

def wait_for_processing(bot_client, request_code: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Ожидает завершения обработки задачи
    Опрашивает статус каждые 2 секунды
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        status_response = bot_client.send_message(f"/status {request_code}")

        # Парсим ответ статуса
        if "обработана успешно" in status_response.lower() or "done" in status_response:
            # Задача завершена - получаем результаты
            result_json = extract_json_from_response(status_response)
            return result_json

        print(f"  Статус: обработка... ({int(time.time() - start_time)}с)")
        time.sleep(2)

    raise TimeoutError(f"Обработка заявки {request_code} истекла (>{timeout}с)")

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Извлекает JSON из ответа бота"""
    import json
    import re

    # Ищем JSON в ответе
    json_match = re.search(r'\{.*?\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: возвращаем минимальный результат
    return {
        "status": "done" if "успешно" in response else "error",
        "items": [],
        "message": response
    }

# Маркеры для pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.iiko,
    pytest.mark.invoice,
]
