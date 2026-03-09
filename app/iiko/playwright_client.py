"""Playwright-клиент для загрузки позиций в iiko UI."""

from playwright.async_api import async_playwright

from app.config import settings
from app.schemas import InvoiceItem


class IikoPlaywrightClient:
    """Автоматизирует работу с iiko через браузер."""

    async def upload_invoice_items(self, items: list[InvoiceItem], username: str, password: str) -> None:
        """Логинится в iiko и добавляет строки накладной в складской модуль."""
        if not settings.iiko_login_url or not username or not password:
            raise RuntimeError("IIKO credentials are not configured")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.iiko_headless)
            page = await browser.new_page()
            try:
                await page.goto(settings.iiko_login_url, wait_until="domcontentloaded")
                await self._login(page, username, password)
                await self._open_inventory_module(page)

                for item in items:
                    await self._create_row(page, item)

                await page.click(settings.iiko_selectors_save)
                await page.wait_for_timeout(1000)
            finally:
                await browser.close()

    async def _login(self, page, username: str, password: str) -> None:
        """Выполняет вход в iiko по набору селекторов и учетных данных."""
        username_selectors = [
            settings.iiko_selectors_username,
            "input[name='username']",
            "input[type='email']",
            "input[autocomplete='username']",
            "input[formcontrolname*='login' i]",
            "input[formcontrolname*='user' i]",
            "input[placeholder*='логин' i]",
            "input[placeholder*='login' i]",
            "mat-form-field input",
        ]
        password_selectors = [
            settings.iiko_selectors_password,
            "input[name='password']",
            "input[type='password']",
            "input[autocomplete='current-password']",
            "input[formcontrolname*='password' i]",
            "input[placeholder*='пароль' i]",
            "input[placeholder*='password' i]",
        ]
        submit_selectors = [
            settings.iiko_selectors_submit,
            "button[type='submit']",
            "button:has-text('Войти')",
            "button:has-text('ВХОД')",
            "button:has-text('Login')",
            "button:has-text('Sign in')",
            "button.mat-mdc-raised-button",
        ]

        await self._fill_first(page, username_selectors, username)
        await self._fill_first(page, password_selectors, password)
        await self._click_first(page, submit_selectors)

    async def _fill_first(self, page, selectors: list[str], value: str) -> None:
        """Заполняет первый найденный инпут из списка селекторов."""
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.fill(value)
                return
        raise RuntimeError(f"No matched input selector from: {selectors}")

    async def _click_first(self, page, selectors: list[str]) -> None:
        """Кликает по первому найденному элементу из списка селекторов."""
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.click()
                return
        raise RuntimeError(f"No matched clickable selector from: {selectors}")

    async def _open_inventory_module(self, page) -> None:
        """Открывает модуль управления складом после логина."""
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1200)

        inventory_selectors = [
            settings.iiko_selectors_inventory,
            "div.item-wrapper:has-text('Управление складом')",
            "p:has-text('Управление складом')",
            "text=Управление складом",
        ]
        await self._click_first(page, inventory_selectors)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)

    async def _create_row(self, page, item: InvoiceItem) -> None:
        """Создает строку накладной на странице склада."""
        await page.click(settings.iiko_selectors_new_row)

        # Selectors below must match your iiko UI structure.
        await page.fill("input[name='name']:visible", item.name)
        if item.unit_amount is not None:
            await page.fill("input[name='unitAmount']:visible", str(item.unit_amount))
        if item.unit_price is not None:
            await page.fill("input[name='unitPrice']:visible", str(item.unit_price))
        if item.supply_quantity is not None:
            await page.fill("input[name='supplyQty']:visible", str(item.supply_quantity))
        if item.cost_without_tax is not None:
            await page.fill("input[name='sumNoTax']:visible", str(item.cost_without_tax))
        if item.cost_with_tax is not None:
            await page.fill("input[name='sumWithTax']:visible", str(item.cost_with_tax))
