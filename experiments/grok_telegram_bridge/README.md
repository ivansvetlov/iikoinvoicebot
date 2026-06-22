# Grok ↔ Telegram Bridge

Удалённый доступ к **локальному Grok CLI** с телефона.

## UI в Telegram

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

После каждого запроса bridge пишет:

```
data/private/grok_bridge/
  HANDOFF_LATEST.md   ← Cursor читает первым дома
  journal.jsonl
  context/<user_id>.jsonl
  runs/<run_id>/      ← prompt, response, git diff
```

См. `agents/REMOTE_HANDOFF.md`.

## Bootstrap (первый запрос после /new)

Автоматически: чтение HANDOFF, DEBUG, TODO, git, health → краткий отчёт → задача.

Метапромпт: `agents/METAPROMPT.md` (через `grok --rules`).

## Запуск

```powershell
.\.venv\Scripts\python.exe -m experiments.grok_telegram_bridge
```

### Прокси (если прямой доступ к Telegram заблокирован)

Добавь в `.env`:

```
GROK_BRIDGE_PROXY=socks5://127.0.0.1:1080
# или
# GROK_BRIDGE_PROXY=http://user:pass@proxy.example.com:8080
```

Bridge будет использовать его для всех запросов к Bot API.
```

To make bridge more resilient to flaky DCs, perhaps we can improve the retry or add user-agent etc, but main is done.

Now, to test syntax of the changes.
## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_grok_bridge -v
```

## Project dashboard (HTML)

Единый файл: roadmap + `logs/` + metrics + reports + online probe + bridge runs.

```powershell
.\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
```

Открыть: `docs/assets/project-dashboard.html` (алиас: `todo-dashboard.html`). Вкладки: Roadmap, Metrics, Logs, Reports, Online, Bridge. Авто-обновление каждые 2 мин (опционально). После каждого Grok run дашборд пересобирается в фоне.
