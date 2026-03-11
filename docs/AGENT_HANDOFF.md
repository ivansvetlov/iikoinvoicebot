# Handoff: что сделано в проекте и где смотреть (для следующего агента)

> Цель этого файла — чтобы новый агент/разработчик за 10–15 минут понял текущее состояние проекта, решения и где искать причины ошибок.

## 0) Главные правила
- Основные правила для агентов/разработчиков: `AGENTS.md` (корень проекта).
- Проверенные команды запуска/диагностики: `DEBUG.md`.

## 0) Важно про секреты
- **Нельзя коммитить**: `.env`, `id_ed25519*`, папки `logs/`, `data/`, `tmp/`, `.venv/`.
- Дамп `dialogue_dump.jsonl` содержит историю и потенциально секреты, поэтому он **в `.gitignore`**.

## 1) Архитектура (как течёт запрос)
**Telegram → Bot → Backend → Queue (Redis/RQ) → Worker → (LLM/OCR/парсинг) → (опционально iiko) → Telegram editMessage**

Ключевые моменты:
- Backend **не** обрабатывает файл синхронно: `/process` и `/process-batch` кладут задачу в очередь и отвечают `status="queued"`.
- Worker (`app/tasks.py`) выполняет обработку и **редактирует** статусное сообщение в Telegram.

## 2) Где главная логика
- `app/services/pipeline.py` — основной пайплайн:
  - извлечение текста/контента;
  - вызов LLM;
  - валидация результата;
  - (опционально) загрузка в iiko.
- `app/api.py` — FastAPI:
  - `/process` (один файл), `/process-batch` (несколько файлов);
  - сохраняет job в `data/jobs/<request_id>/` и кладёт задачу в очередь.
- `app/tasks.py` — воркер:
  - читает payload, вызывает pipeline, пишет в БД (TaskRecord), редактирует сообщение в Telegram.
- `app/bot/manager.py` — логика Telegram:
  - поддержка фото/документов;
  - media group (альбом) → `/process-batch`;
  - `/split` + `/done` режим для склейки частей;
  - rate-limit/идемпотентность/логирование событий.
- `app/bot/backend_client.py` — HTTP‑клиент для `/process` и `/process-batch` (бот → backend).
- `app/bot/file_storage.py` — файловое хранилище pending/split (bot side).
- `docs/_md/root/ARCHITECTURE.md` — краткий обзор модулей и потоков.

## 3) Что добавили для устойчивости (негативные кейсы)
### 3.1 User-friendly ошибки + error_code
- В API-ответах есть `error_code` (машиночитаемый код), по нему бот показывает подсказки.
- Ошибки форматируются без стектрейсов.

### 3.2 Защита от «зацикливания» LLM
Причина бага: LLM может начать повторять строки (например, "Масса брутто" и нули), раздувать ответ до лимита и отдавать **обрезанный JSON**.

Сделано:
- `max_output_tokens` уменьшен до **1000**;
- в function schema ограничены `items` через `maxItems` (см. `pipeline.py`);
- добавлен детектор мусора (`llm_garbage` / `llm_bad_response`).

## 4) Коды заявок: длинный request_id vs короткий код
- Внутренний `request_id` длинный и нужен системе (уникальность, папки jobs, БД).
- Пользователю показываем коротко: **`HHMMSS_mmm`** (например `000736_800`).

### Единый формат сообщений
Сделано так, чтобы бот и воркер форматировали сообщения одинаково:
- `app/utils/user_messages.py`:
  - `short_request_code(request_id)`
  - `format_user_response(payload)`

## 5) Диагностика по коду заявки (самый полезный инструмент)
Скрипт:
- `scripts/diagnose_request.py`

Он принимает:
- полный request_id
- короткий код (`000736_800`)
- или строку целиком (`Код заявки: 000736_800`)

И печатает + сохраняет отчёт:
- `tmp/diagnose_<request_id>.json`

## 6) Veai workflows (подсказки в IDE)
См. `.veai/workflows/`:
- `Диагностика_request_id.md`
- `Регрессия_смоук_чек.md`
- `Откат_через_git_безопасно.md`

## 7) Git-процесс (как не бояться откатов)
- `main` — стабильная ветка.
- Тег стабильной точки: `stable-2026-03-09`.
- Текущая работа: ветка `feature/stage4-reliability-observability`.

## 8) Известные проблемы/заметки
- **Media group альбом**: если backend сохраняет файлы по одинаковому имени, возможна перезапись. `/split` сохраняет уникальные имена и надёжнее.
- Если видите мусор вроде "Масса брутто" — это признак того, что на вход пришла часть таблицы без контекста (вертикальные полосы). Лучше цельный кадр/ PDF.

## 9) Недавние изменения (2026-03-10)
- Переработан pending-UX в боте: вместо скрытого таймера — явные кнопки "Обработать/Добавить ещё", и явный выбор режима при 2+ файлах. Файлы: `app/bot/manager.py`, `app/bot/backend_client.py`, `app/bot/file_storage.py`.
- Лог стоимости LLM переведён в append-only (без перечтения CSV). Файл: `app/services/pipeline.py`.
- `.env` читается с `utf-8-sig` из-за BOM; добавлены утилиты `scripts/check_bom.py` и `scripts/strip_bom.py`.
- Архитектурный обзор перенесён в `docs/_md/root/ARCHITECTURE.md`.
- Добавлен `.gitattributes` для LF в репозитории; локально `core.autocrlf=false` рекомендован для чистых диффов.
- Добавлен `logs/llm_costs_summary.json` (итоги LLM без пересчёта CSV) + `scripts/llm_costs_rebuild.py` для пересборки.
- Упрощён UX: убран режим `/multi`, в split добавлены кнопки «Завершить/Добавить ещё/Отменить».
- `/start` теперь очищает pending/split буферы, чтобы не тянуть старые файлы.

Проверка: запустить `python bot.py`, отправить 1 файл и убедиться, что появляется явная клавиатура "Обработать/Добавить ещё"; отправить 2 файла — увидеть выбор "Объединить/Раздельно".

---

### Быстрый чек-лист для нового агента
1) Прочитать этот файл.
2) Открыть `pipeline.py`, найти настройки LLM (max_output_tokens/maxItems) и детектор мусора.
3) При любой проблеме — взять код заявки и запустить `scripts/diagnose_request.py`.

## 10) Recent changes (2026-03-11)
- Improved image preprocessing for recognition: auto-crop white document area, autocontrast, upscale, unsharp mask.
  Files: `app/services/pipeline.py`.
- Default image model set to `gpt-4o` via `OPENAI_MODEL_IMAGE` to improve OCR-heavy accuracy.
- Increased cropped image upscale cap and sharpening; JPEG quality raised for better numeric legibility.
- Settings now ignore empty environment variables (`env_ignore_empty=True`) so `.env` values are not overridden by blank envs.
- If image parse looks like garbage or empty after preprocessing, the pipeline retries once with the raw image.
- Added stronger prompt guardrails to avoid placeholder/empty rows.
- Prompt now explicitly forbids semantic substitution of item names.
- Added garbage detection for many empty rows.
- Added optional OCR hint for images (pytesseract + system Tesseract). Flag: `ENABLE_IMAGE_OCR_HINT`.
- Added header-number leak detector (1..15 column index row) with prompt retry.
- If OCR text includes a header line with column numbers (1..15), it is passed as an alignment hint.
- Added repeated numeric column detector (e.g., same price/total across rows) with prompt retry.
- Updated `docs/BOT_COMMAND_MATRIX.md` with current UX behavior (single/multi/split/PDF).
- TODO: marked split-album aggregation as done.
- Synced docs: updated `AGENTS.md`, `docs/DEV_SETUP.md`, `docs/_md/root/ARCHITECTURE.md`, `TESTCASES.md` to match current UX and run config usage.

## 11) Recognition focus: iiko target fields (2026-03-11)
- LLM schema now targets explicit item fields: `name`, `quantity`, `mass`, `unit_price`, `amount_without_tax`, `tax_rate`, `tax_amount`, `amount_with_tax`.
- Mapping: `quantity -> unit_amount`, `mass -> supply_quantity`, `amount_without_tax -> cost_without_tax`, `amount_with_tax -> cost_with_tax/total_cost`.
- Basic derivations added: compute missing `amount_with_tax`/`tax_amount`/`tax_rate` when possible.
- User-facing invoice formatting shows mass, sum без НДС, НДС %, НДС сумма, сумма с НДС.
- Image preprocessing now attempts OCR-based header detection to crop above the table header with safe padding. If OCR is unavailable, it falls back to line-based grid detection (horizontal/vertical runs).
- Cropped images allow a larger upscale cap (`IMAGE_MAX_DIM_CROPPED`) to improve readability of small tables.
- Added `TESSERACT_CMD` config and auto-detection of common Windows install paths for OCR.
- Image model overrides: `OPENAI_MODEL_IMAGE` and optional `OPENAI_MODEL_IMAGE_FALLBACK` for stronger retries on OCR-heavy images.

## 12) Event codes centralization (2026-03-11)
- Файлы:
  - добавлен `app/bot/event_codes.py` (единый реестр `BOT_*` + helper форматирования);
  - добавлен `docs/BOT_EVENT_CODES.md` (каноническое описание кодов и статусов active/archive);
  - обновлены `app/bot/manager.py`, `DEBUG.md`, `docs/_md/root/README.md`, `docs/_md/root/TODO.md`.
- Поведение:
  - пользовательские сообщения с `Код события: BOT_*` формируются через единый helper (`append_event_code`);
  - активные коды (`BOT_BACKEND_UNAVAILABLE`, `BOT_RATE_LIMIT`, `BOT_NO_PENDING`) собраны в одном месте;
  - `BOT_PENDING_TIMEOUT` зафиксирован как архивный (не эмитится с перехода на явный pending UX).
- Быстрая проверка:
  - `python -m compileall app\bot\event_codes.py app\bot\manager.py`
  - открыть `docs/BOT_EVENT_CODES.md` и сверить коды с `app/bot/event_codes.py`.

## 13) Stage 4 completed: reliability + observability (2026-03-11)
- Файлы:
  - добавлен `app/observability.py` (единое логирование, алерты, метрики);
  - добавлены `scripts/metrics_report.py`, `scripts/export_user_messages.py`;
  - добавлен `docs/BOT_MESSAGE_CATALOG.md`;
  - обновлены `app/api.py`, `app/tasks.py`, `bot.py`, `worker.py`, `app/config.py`, `.env.example`;
  - обновлены `DEBUG.md`, `docs/DEV_SETUP.md`, `docs/_md/root/ARCHITECTURE.md`, `docs/_md/root/README.md`, `docs/_md/root/TODO.md`;
  - удалена мёртвая папка `app/logs/`.
- Поведение:
  - backend/worker/bot пишут логи через единый observability-слой в `logs/*.log` + общий `logs/errors.log`;
  - включены алерты в `logs/alerts.jsonl` (c cooldown и optional Telegram через `ALERTS_TELEGRAM_CHAT_ID`);
  - включен мониторинг времени/ошибок в `logs/metrics.jsonl`, доступен `/metrics/summary` и `scripts/metrics_report.py`;
  - все чекбоксы Этапа 4 отмечены как выполненные в `docs/_md/root/TODO.md`;
  - тексты пользовательских сообщений вынесены в отдельный каталог `docs/BOT_MESSAGE_CATALOG.md` (обновляется скриптом).
- Быстрая проверка:
  - `python -m compileall app\observability.py app\api.py app\tasks.py bot.py worker.py scripts\metrics_report.py scripts\export_user_messages.py`
  - `curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"`
  - `python scripts\metrics_report.py --minutes 60`
  - `python scripts\export_user_messages.py`
