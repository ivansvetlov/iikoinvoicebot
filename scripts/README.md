# Папка `scripts/`

Вспомогательные скрипты для разработчика и эксплуатации.

Основные:
- `diagnose_request.py` — диагностика по `request_id`/коду заявки:
  - читает `TaskRecord` из БД,
  - читает payload из `data/jobs/<request_id>/payload.json`,
  - проверяет `logs/llm_costs.csv`, хвост логов бота/backend,
  - пишет отчёт в `tmp/diagnose_<request_id>.json`.
- `metrics_report.py` — сводка по `logs/metrics.csv` (или `metrics.jsonl`) с ошибками/временем обработки, p50/p95.
- `archive_logs.py` — архивирование старых логов в `logs/archive/` (gzip).
- `dump_task_results.py` — выгрузка `result_json` задач в читаемый JSON.
- `llm_costs_rebuild.py` — пересборка `logs/llm_costs_summary.json` из CSV.
- `git.ps1` — враппер над git, использующий встроенный git из GitHub Desktop.
- `set_mode.ps1` — переключение режима polling/webhook (правит `.env`).

Сюда же можно добавлять другие dev-скрипты (миграции, утилиты и т.д.).
