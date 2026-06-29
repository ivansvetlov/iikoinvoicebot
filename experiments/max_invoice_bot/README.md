# MAX Invoice Bot

Полный порт invoice-бота для мессенджера MAX. **Telegram (`app/bot/manager.py`) не изменяется.**

## Запуск

```powershell
# .env
MAX_INVOICE_BOT_TOKEN=          # business.max.ru после модерации
# MAX_INVOICE_BOT_ALLOWED_USER_IDS=123456   # опционально
BACKEND_URL=http://127.0.0.1:8000
# + OPENAI, IIKO, как для TG

# Backend + worker (как обычно)
.\.venv\Scripts\python.exe scripts\dev_run_all.py

# MAX-бот (отдельный процесс)
.\.venv\Scripts\python.exe -m experiments.max_invoice_bot
```

Или: `.\scripts\run_max_invoice_bot.ps1`

## Архитектура

- План: `docs/planning/INVOICE_BOT_MAX_PORT_PLAN.md`
- Детали: `experiments/max_invoice_bot/ARCHITECTURE.md`

## Отличие от Telegram

| | Telegram | MAX |
|---|----------|-----|
| Результат worker | push в TG API (`chat_id`) | poll `task_store` + доставка в MAX |
| user_id в БД | `6106711925` | `max:6106711925` |
| SDK | aiogram | maxapi |

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_max_invoice_bot -v
```
