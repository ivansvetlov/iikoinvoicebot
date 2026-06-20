# Grok ↔ Telegram Bridge

Удалённый доступ к **локальному Grok CLI** с телефона.

## UI в Telegram

**Inline-кнопки** (не только команды):

| Кнопка | Действие |
|--------|----------|
| 🆕 Новая сессия | сброс + bootstrap при следующем тексте |
| 📊 Статус | git, session, bootstrap |
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

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_grok_bridge -v
```

## TODO dashboard (HTML)

```powershell
.\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
```

Открыть: `docs/assets/todo-dashboard.html` (поиск, фильтры, collapsible секции).
