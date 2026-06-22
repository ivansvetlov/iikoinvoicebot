# Grok ↔ MAX Bridge

Удалённый доступ к **локальному Grok CLI** через мессенджер MAX.
Bot API на `platform-api.max.ru` — **без VPN** (в отличие от Telegram).

Параллельная ветка к `experiments/grok_telegram_bridge` — тот же функционал, другой канал.

Подробнее: [ARCHITECTURE.md](ARCHITECTURE.md) (сверка с официальной документацией MAX).

## Официальная документация MAX

| Раздел | URL | Что важно для bridge |
|--------|-----|----------------------|
| API | https://dev.max.ru/docs-api | `Authorization` header, 30 rps, 4000 chars, inline keyboard |
| Подготовка бота | https://dev.max.ru/docs/chatbots/bots-coding/prepare | токен после модерации, polling vs webhook |
| Создание бота | https://dev.max.ru/docs/chatbots/bots-create | профиль на business.max.ru, статусы модерации |
| Python SDK | https://github.com/max-messenger/max-botapi-python | `maxapi` — используем в `bot.py` |

## UI в MAX

**Inline-кнопки** (не только команды):

| Кнопка | Действие |
|--------|----------|
| 🆕 Новая сессия | сброс + bootstrap при следующем тексте |
| 📊 Статус | git, session, bootstrap |
| 🖥️ Дашборд | обновить + сводка `project-dashboard.html` |
| 🔄 Обновить HTML | пересобрать дашборд |
| 📜 Логи / 📈 Метрики / 📋 Отчёты | превью из `logs/`, metrics, tmp/ |
| ✅/⛔ YOLO | `--always-approve` |
| 🔍 Проверить | следующий текст с `--check` |
| 📋 Контекст | последние ходы диалога |
| 🏠 Handoff | `HANDOFF_LATEST.md` для Cursor |
| 📓 Журнал | последние runs |

## Remote ↔ Home

```
data/private/grok_max_bridge/
  HANDOFF_LATEST.md   ← Cursor читает первым дома
  journal.jsonl
  context/<user_id>.jsonl
  runs/<run_id>/
```

## Получение токена (чеклист)

По [prepare](https://dev.max.ru/docs/chatbots/bots-coding/prepare):

1. Верифицированный профиль на [business.max.ru](https://business.max.ru/self)
2. **Чат-боты → Создать** → дождаться модерации (статус «создан»)
3. **Чат-боты → Перейти → Расширенные настройки → Настроить** → скопировать токен
4. Узнать свой `user_id` (придёт в событии `bot_started` / `message_created` в логах при первом контакте)
5. В `.env`:
   ```
   GROK_MAX_BRIDGE_TOKEN=<токен>
   GROK_MAX_BRIDGE_ALLOWED_USER_IDS=<user_id>
   ```

Токен — прямой доступ к боту. Не коммитить, не светить в чатах.

## Запуск

```powershell
.\.venv\Scripts\python.exe -m experiments.grok_max_bridge
```

При старте bridge:
- вызывает `delete_webhook()` (polling и webhook нельзя одновременно)
- использует Long Polling `GET /updates` (режим dev, как рекомендовано для разработки)

**Production (когда будет сервер):** только Webhook через `POST /subscriptions` + HTTPS. См. ARCHITECTURE.md.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_grok_max_bridge -v
```

## Связь с roadmap проекта

- Ветка канала: `feature/channel-max` (см. `docs/planning/TODO.md`, этап 8)
- Invoice-бот через MAX — отдельный трек (этап 8); этот bridge — **Grok remote agent**, не invoice flow
