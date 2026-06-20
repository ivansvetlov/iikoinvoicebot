# Remote ↔ Home handoff

## Пять вариантов (оценка)

| # | Вариант | Плюсы | Минусы | Вердикт |
|---|---------|-------|--------|---------|
| 1 | Полный дамп Telegram-чата | Всё видно | Шум, нет git, тяжёлый | ❌ |
| 2 | Только git commits `[tg]` | Чистая история | Агент не всегда коммитит | Дополнение |
| 3 | Grok session export | Богатый trace | Привязка к CLI, не структура | Дополнение |
| 4 | **Journal + HANDOFF_LATEST + runs/** | Структура, git diff, preview | Нужна дисциплина записи | ✅ **выбрано** |
| 5 | Live terminal tail | Real-time | Только дома, не async | ❌ для дороги |

## Реализация (вариант 4)

```
data/private/grok_bridge/
  HANDOFF_LATEST.md      ← Cursor читает первым
  journal.jsonl          ← все runs (append-only)
  context/<user>.jsonl   ← диалог для кнопки Context
  runs/<run_id>/
    meta.json
    prompt.txt
    response.txt
    git_before.json / git_after.json
    git_diff.patch
```

Bridge пишет автоматически после каждого `grok -p`.
METAPROMPT требует дополнять HANDOFF_LATEST секцией «Для Cursor» после значимых задач.

## Workflow

**Дорога (TG):** задача → grok → journal + HANDOFF_LATEST.

**Дом (Cursor):** `HANDOFF_LATEST.md` → `git status` → `runs/<id>/` → продолжить.

## Dashboard (видимость с дороги и дома)

Единый HTML — не отдельный сайт, а расширение TODO-dashboard:

| Источник | Вкладка |
|----------|---------|
| `docs/planning/TODO.md` | Roadmap |
| `logs/*.log`, metrics | Metrics, Logs |
| `tmp/availability_*`, diagnose | Online, Reports |
| `data/private/grok_bridge/` | Bridge, Reports |

Файл: `docs/assets/project-dashboard.html` (генератор: `scripts/render_todo_dashboard.py`).

**TG-кнопки:** Дашборд (сводка + путь), Логи, Метрики, Отчёты, Обновить HTML. После каждого run — фоновая пересборка.
