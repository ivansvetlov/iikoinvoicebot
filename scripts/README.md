# Папка `scripts/`

Вспомогательные скрипты для разработчика и эксплуатации.

Основные:
- `diagnose_request.py` — диагностика по `request_id`/коду заявки:
  - читает `TaskRecord` из БД,
  - читает payload из `data/jobs/<request_id>/payload.json`,
  - проверяет `logs/llm_costs.csv`, хвост логов бота/backend,
  - пишет отчёт в `tmp/diagnose_<request_id>.json`.
- `dump_task_results.py` — выгрузка `result_json` задач в читаемый JSON.
- `git.ps1` — враппер над git, использующий встроенный git из GitHub Desktop.
- `set_mode.ps1` — переключение режима polling/webhook (правит `.env`).

Сюда же можно добавлять другие dev-скрипты (миграции, утилиты и т.д.).
