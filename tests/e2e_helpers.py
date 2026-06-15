"""
Вспомогательные классы и функции для E2E тестирования
"""

# tests/e2e/helpers/telegram_client.py
class TelegramBotClient:
    """Клиент для отправки сообщений и документов боту"""

    def __init__(self, bot_token: str, user_id: str, dev_mode: bool = True):
        self.bot_token = bot_token
        self.user_id = user_id
        self.dev_mode = dev_mode
        self.chat_history = []

    def send_document(self, document_bytes: bytes, filename: str = "test_invoice.pdf") -> str:
        """Отправляет документ боту и возвращает ответ"""
        import requests

        url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"

        files = {"document": (filename, document_bytes, "application/pdf")}
        data = {"chat_id": self.user_id}

        response = requests.post(url, data=data, files=files)
        response_json = response.json()

        self.chat_history.append({
            "type": "document",
            "filename": filename,
            "timestamp": str(datetime.now())
        })

        # Ждем ответа бота
        import time
        time.sleep(2)  # Даем боту время на ответ

        # Получаем последнее сообщение
        last_message = self.get_last_message()
        return last_message

    def send_message(self, text: str) -> str:
        """Отправляет текстовое сообщение боту"""
        import requests

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.user_id,
            "text": text
        }

        response = requests.post(url, json=data)

        self.chat_history.append({
            "type": "message",
            "text": text,
            "timestamp": str(datetime.now())
        })

        # Ждем ответа
        import time
        time.sleep(1)

        return self.get_last_message()

    def get_last_message(self) -> str:
        """Получает последнее полученное сообщение от бота"""
        import requests

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"limit": 1}

        response = requests.get(url, params=params)
        updates = response.json()["result"]

        if updates:
            message = updates[-1]
            if "message" in message:
                return message["message"].get("text", "")

        return ""


# tests/e2e/helpers/iiko_web_helper.py
class IikoWebHelper:
    """Помощник для проверки результатов через iiko Web UI"""

    def __init__(self, base_url: str, crmid: str):
        self.base_url = base_url
        self.crmid = crmid
        self.session = None
        self._authenticate()

    def _authenticate(self):
        """Авторизуется в iiko через обычный бот API"""
        from app.iiko.server_client import IikoServerClient

        self.iiko_client = IikoServerClient(
            base_url=self.base_url.replace("/iikoweb", ""),  # Преобразуем URL
            username="user",
            password="user#test"  # Из demo stand
        )

        # Авторизуемся
        token = self.iiko_client.authenticate()
        if not token:
            raise RuntimeError("Не удалось авторизоваться в iiko")

    def get_all_products(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получает список всех товаров из iiko"""
        try:
            products = self.iiko_client.get_products()
            return products[:limit]
        except Exception as e:
            print(f"Ошибка получения товаров: {e}")
            return []

    def get_product(self, name: str) -> Dict[str, Any]:
        """Получает информацию о товаре по названию"""
        products = self.get_all_products()
        for product in products:
            if product.get("name").lower() == name.lower():
                return product
        return None

    def get_stock_by_product_id(self, product_id: str) -> Dict[str, Any]:
        """Получает баланс товара по ID"""
        try:
            stock = self.iiko_client.get_stock_balance(product_id=product_id)
            return stock
        except Exception as e:
            print(f"Ошибка получения баланса: {e}")
            return {"quantity": 0}

    def get_stock_by_document(self, document_number: str) -> List[Dict[str, Any]]:
        """Получает все позиции по номеру документа"""
        try:
            items = self.iiko_client.get_document_items(document_number)
            return items
        except Exception as e:
            print(f"Ошибка получения позиций: {e}")
            return []

    def get_valid_units(self) -> List[str]:
        """Получает валидные единицы измерения для iiko"""
        return ["шт", "кг", "л", "г", "мл", "упаковка", "ящик"]


# tests/e2e/helpers/invoice_generator.py
class InvoiceGenerator:
    """Генератор тестовых накладных в PDF формате"""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def create_pdf_invoice(self,
                          date: str = None,
                          supplier: str = "Тестовый поставщик",
                          items: List[Dict] = None,
                          **kwargs) -> bytes:
        """Генерирует PDF накладную"""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from io import BytesIO

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        if items is None:
            items = []

        # Создаем PDF в памяти
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)

        # Заголовок
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, "НАКЛАДНАЯ")

        # Информация
        c.setFont("Helvetica", 10)
        c.drawString(50, 720, f"Дата: {date}")
        c.drawString(50, 700, f"Поставщик: {supplier}")

        # Таблица товаров
        c.setFont("Helvetica-Bold", 10)
        y = 670
        c.drawString(50, y, "№")
        c.drawString(80, y, "Товар")
        c.drawString(350, y, "Кол-во")
        c.drawString(420, y, "Ед.изм")
        c.drawString(480, y, "Цена")
        c.drawString(540, y, "Сумма")

        c.setFont("Helvetica", 9)
        y = 650

        for i, item in enumerate(items, 1):
            name = item.get("name", "")[:40]  # Обрезаем длинные названия
            qty = item.get("qty", 0)
            unit = item.get("unit", "шт")
            price = item.get("price", 0)
            total = qty * price

            c.drawString(50, y, str(i))
            c.drawString(80, y, name)
            c.drawString(350, y, str(qty))
            c.drawString(420, y, unit)
            c.drawString(480, y, f"{price:.2f}")
            c.drawString(540, y, f"{total:.2f}")

            y -= 20
            if y < 50:  # Переход на следующую страницу
                c.showPage()
                y = 750

        c.save()
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()


# tests/e2e/helpers/assertions.py
class E2ETestAssertions:
    """Кастомные проверки для E2E тестов"""

    def assert_invoice_recognized(self, result: Dict[str, Any]):
        """Проверяем что накладная распознана"""
        assert result.get("status") in ["done", "processing"], \
            f"Статус должен быть 'done' или 'processing', получено: {result.get('status')}"
        assert len(result.get("items", [])) > 0, \
            "Должны быть распознаны товары"

    def assert_items_count(self, result: Dict[str, Any], expected_count: int):
        """Проверяем количество товаров"""
        actual_count = len(result.get("items", []))
        assert actual_count == expected_count, \
            f"Ожидается {expected_count} товаров, получено {actual_count}"

    def assert_no_duplicates(self, items: List[Dict], iiko_total_qty: int, expected_qty: int):
        """Проверяем что нет дубликатов"""
        assert iiko_total_qty == expected_qty, \
            f"Количество в iiko должно быть {expected_qty}, получено {iiko_total_qty}. " \
            f"Возможно дубликаты или ошибка маппинга"

    def assert_mapping_valid(self, item: Dict[str, Any]):
        """Проверяем что маппинг товара валиден"""
        assert item.get("iiko_product_id"), \
            f"Товар {item.get('name')} не замаплен (нет iiko_product_id)"
        assert item.get("qty", 0) > 0, \
            f"Количество должно быть > 0, получено {item.get('qty')}"


from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
