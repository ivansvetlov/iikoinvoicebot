# Handoff: что сделано в проекте и где смотреть (для следующего агента)

> Цель этого файла — чтобы новый агент/разработчик за 10–15 минут понял текущее состояние проекта, решения и где искать причины ошибок.

## 49) iiko transport: Playwright removed, API-first mode (2026-04-18)
- Files:
  - removed `app/iiko/playwright_client.py`;
  - added `app/iiko/server_client.py`;
  - updated `app/config.py`, `.env.example`, `requirements.txt`, `app/services/pipeline.py`.
- Behavior:
  - browser automation path is removed from runtime;
  - direct iiko upload now goes through server-side HTTP client (`IIKO_TRANSPORT=api`);
  - safe default mode is `IIKO_TRANSPORT=import_only` with CSV/XLSX fallback generation.
- Notes:
  - current `iiko_server_docs` cache does not provide full endpoint/payload contracts;
  - integration gaps are listed in `docs/IIKO_API_GAPS.md`.

## 0) Главные правила
- Основные правила для агентов/разработчиков: `docs/AGENTS.md`.
- Проверенные команды запуска/диагностики: `docs/DEBUG.md`.

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
- `docs/ARCHITECTURE.md` — краткий обзор модулей и потоков.

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
- Пользователю показываем коротко: **5 цифр** (например `48291`).

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
- короткий код (`48291`)
- или строку целиком (`Код заявки: 48291`)

И печатает + сохраняет отчёт:
- `tmp/diagnose_<request_id>.json`

## 6) IDE workflows
- Воркфлоу Veai удалены из репозитория как неиспользуемые.
- Для операционных сценариев используйте `docs/DEBUG.md` и `docs/DEV_SETUP.md`.

## 7) Git-процесс (как не бояться откатов)
- `main` — стабильная ветка.
- Тег стабильной точки: `stable-2026-03-09`.
- Текущая работа по сообщениям/коротким кодам: ветка `feature/ui-messages`.

## 8) Известные проблемы/заметки
- **Media group альбом**: если backend сохраняет файлы по одинаковому имени, возможна перезапись. `/split` сохраняет уникальные имена и надёжнее.
- Если видите мусор вроде "Масса брутто" — это признак того, что на вход пришла часть таблицы без контекста (вертикальные полосы). Лучше цельный кадр/ PDF.

## 9) Недавние изменения (2026-03-10)
- Переработан pending-UX в боте: вместо скрытого таймера — явные кнопки "Обработать/Добавить ещё", и явный выбор режима при 2+ файлах. Файлы: `app/bot/manager.py`, `app/bot/backend_client.py`, `app/bot/file_storage.py`.
- Лог стоимости LLM переведён в append-only (без перечтения CSV). Файл: `app/services/pipeline.py`.
- `.env` читается с `utf-8-sig` из-за BOM; добавлены утилиты `scripts/check_bom.py` и `scripts/strip_bom.py`.
- Архитектурный обзор перенесён в `docs/ARCHITECTURE.md`.
- Добавлен `.gitattributes` для LF в репозитории; локально `core.autocrlf=false` рекомендован для чистых диффов.
- Добавлен `logs/llm_costs_summary.json` (итоги LLM без пересчёта CSV) + `scripts/llm_costs_rebuild.py` для пересборки.
- Упрощён UX: убран режим `/multi`, в split добавлены кнопки «Завершить/Добавить ещё/Отменить».
- `/start` теперь очищает pending/split буферы, чтобы не тянуть старые файлы.

Проверка: запустить `python app/entrypoints/bot.py`, отправить 1 файл и убедиться, что появляется явная клавиатура "Обработать/Добавить ещё"; отправить 2 файла — увидеть выбор "Объединить/Раздельно".

## 10) Recognition iteration update (2026-04-05)
- Файлы:
  - обновлены `app/services/pipeline.py`, `app/services/invoice_validator.py`, `app/bot/manager.py`, `app/schemas.py`;
  - добавлены/обновлены проверки в `tests/test_invoice_recognition.py`;
  - добавлен диагностический скрипт `scripts/diagnose_image.py`.
- Поведение:
  - чеки (кассовые/товарные) больше не отсекаются как `not_invoice` при наличии товарных строк;
  - добавлена явная поддержка `Форма 1-Т` (TTN) по аналогии с `ТОРГ-12` в промпте и нормализации `document_type`;
  - для Excel-шаблонов без заполненных строк возвращается понятный результат «шаблон распознан» вместо ошибочного `not_invoice`;
  - добавлены ретраи LLM для truncated output (`max_output_tokens`) и debug snapshots в `tmp/llm_debug`.
- Git/ветки:
  - текущий рабочий трек распознавания: `feature/recognition-improvements`;
  - ветка `exp/topic-mcp-iiko-gateway` признана отдельным контекстом (не для recognition-задач);
  - статусы и новые этапы (MAX, МойСклад, 1С, коммерциализация) добавлены в `docs/TODO.md`.

## 11) Roadmap refocus (2026-04-06)
- В `docs/TODO.md` уточнён приоритет: масштабирование через процессные модели (`cross-vertical modeling`), а не через набор разрозненных фич.
- Voice-сценарии зафиксированы как канал входа в унифицированный процессный конвейер, а не отдельный продукт.
- В интеграционном треке добавлен явный контур `iiko + r_keeper/StoreHouse + МойСклад + 1С` с приоритетом для РФ-сегмента: `MAX + МойСклад + 1С`.

## 12) Stage 3 final closure (2026-04-06)
- Stage 3 в `docs/TODO.md` помечен как закрытый по MVP scope.
- Невыполненные ранее пункты Stage 3 (`гибридный парсер`, `метрики стоимости`) перенесены в `Этап 12 — Post-stage3 optimization backlog`.

## 13) Post-stage3 backlog execution (2026-04-06)
- В `pipeline.py` добавлен гибридный контур: быстрый `InvoiceParser` для `text/docx/pdf/excel` и fallback в LLM при неуспехе fast-path.
- Cost summary (`logs/llm_costs_summary.json`) расширен агрегатами `by_day` и `by_user`; обновлён `scripts/llm_costs_rebuild.py`.
- Для новых сценариев добавлены тесты в `tests/test_invoice_recognition.py` (fast-parser path + cost summary aggregates).

## 14) Stage 4 reliability & observability closure (2026-04-06)
- Добавлен единый модуль наблюдаемости `app/observability.py`:
  - централизованная настройка логов (`configure_logging`) для backend/bot/worker;
  - алерт-канал `logs/alerts.jsonl` + `logs/alerts.csv` (автоматически пишет ERROR/CRITICAL);
  - метрики `logs/metrics.jsonl` + `logs/metrics.csv` (`track_metric`, `measure_time`);
  - архивирование старых логов (`archive_logs`).
- Точки входа переведены на единый logging: `app/api.py`, `app/entrypoints/bot.py`, `app/entrypoints/worker.py`.
- Добавлен middleware в backend для метрик HTTP времени/статусов (`http_request`).
- Добавлены метрики воркера (`worker_job`) в `app/tasks.py` (время обработки, статус, error_code).
- Коды событий бота вынесены в `app/bot/event_codes.py`; справочник добавлен в `docs/BOT_EVENT_CODES.md`.
- Добавлены скрипты:
  - `scripts/metrics_report.py` (сводка p50/p95 и ошибок);
  - `scripts/archive_logs.py` (архивация логов в `logs/archive/`).
- `docs/DEV_SETUP.md` дополнен повторяемым чек-листом старта для нового разработчика.

## 15) Stage 5 UX closure (2026-04-06)
- Файлы:
  - обновлён `app/bot/manager.py` (split-агрегация альбомов, мягкая дедупликация, flush split-альбомов перед `/done`);
  - добавлены контрольные файлы `fixtures/smoke/invoice_control.txt`, `fixtures/smoke/receipt_control.txt`, `fixtures/smoke/duplicate_blob.bin`;
  - добавлен тестовый модуль `tests/test_bot_stage5.py`;
  - обновлён статус в `docs/TODO.md` (три незакрытых пункта Stage 5 отмечены как выполненные).
- Поведение:
  - в split-режиме альбом (`media_group`) больше не спамит серией prompt-сообщений: обновление прогресса делается один раз после сборки группы;
  - дедупликация работает в soft-режиме: дубликаты не блокируются, но пользователь получает предупреждение, и событие фиксируется в mailbox-логе;
  - при `/done` сначала принудительно дозавершается незакрытый split-альбом, чтобы не потерять последние фото/файлы.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 16) Stage 5 UX refinements after live feedback (2026-04-06)
- Файлы:
  - обновлены `app/bot/manager.py`, `app/utils/user_messages.py`, `app/bot/file_storage.py`;
  - добавлен тест `tests/test_user_messages.py`.
- Поведение:
  - тексты soft-дедупликации переформулированы в человеко-понятный вид (`среди отправленных фото/файлов есть дубликаты`), без блокировки;
  - split-подсказка теперь явно объясняет, что это черновик `/split`, как завершить (`✅ Завершить`/`/done`) и как очистить (`✖ Отменить`/`/cancel`);
  - из split-клавиатуры убрана лишняя кнопка «Добавить ещё» (отправка дополнительных файлов и так работает);
  - в сообщениях редактирования накладной и ответах отправки в iiko добавлен короткий `Код заявки` (5 цифр).
  - исправлена потенциальная потеря файлов при очень быстрых загрузках с одинаковыми именами: сохранение pending/split теперь с `uuid`-nonce в имени файла.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 17) Pending UX wording update (2026-04-06)
- Файлы:
  - обновлён `app/bot/manager.py` (тексты и подписи pending-кнопок).
- Поведение:
  - кнопка `mode:merge` переименована в `🟩 Объединить и отправить` (визуально “зелёный” CTA);
  - `Добавить ещё` переименовано в `🕒 Добавлю ещё позже`, чтобы явно показать смысл: это сохранение черновика без отправки;
  - подсказки для pending-режима уточнены: когда нажимать объединение и что происходит с черновиком.

## 18) Request code format update (2026-04-06)
- Файлы:
  - обновлены `app/utils/user_messages.py`, `scripts/diagnose_request.py`, `docs/DEBUG.md`.
- Поведение:
  - пользовательский `Код заявки` переведён в формат **5 цифр** (вместо `HHMMSS_mmm`);
  - `scripts/diagnose_request.py` поддерживает и новый 5-значный код, и legacy-код `HHMMSS_mmm`;
  - при совпадении нескольких заявок по короткому коду выбирается самая свежая, альтернативы выводятся в консоль.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_user_messages -v`
  - `.venv\\Scripts\\python.exe scripts\\diagnose_request.py <5-digit-code>`

## 19) Explicit buffer dedup action (2026-04-06)
- Файлы:
  - обновлены `app/bot/file_storage.py`, `app/bot/manager.py`, `tests/test_bot_stage5.py`.
- Поведение:
  - добавлена явная кнопка `🧹 Удалить дубликаты` в split-черновике и pending-черновике;
  - удаление дублей теперь управляемо пользователем: показываем, сколько удалено и сколько файлов осталось в черновике;
  - дубли определяются по содержимому файла (sha256), сохраняется первый экземпляр.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 -v`

## 20) Pending/Split UX cleanup after feedback (2026-04-06)
- Файлы:
  - обновлены `app/bot/manager.py`, `app/bot/file_storage.py`, `tests/test_bot_stage5.py`.
- Поведение:
  - из pending-клавиатуры убрана кнопка `🕒 Добавлю ещё позже`; добавление файлов работает по умолчанию без отдельного действия;
  - кнопка `🧹 Удалить дубликаты` в pending/split показывается только если в текущем черновике реально есть дубликаты;
  - тексты подсказок упрощены для пользователя: отдельной строкой указано, что можно дослать файлы или отправить в обработку.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`

## 21) Merge CTA flow fix (2026-04-06)
- Файлы:
  - обновлены `app/bot/manager.py`, `tests/test_bot_stage5.py`.
- Поведение:
  - `🟩 Объединить и отправить` в pending больше не переводит в промежуточный split-экран;
  - по кнопке сразу отправляется единый batch в backend (без лишнего шага `Отменить/Завершить`);
  - текст `split:cancel` переписан: теперь явно сказано, что черновик очищен и можно отправлять новые файлы.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`

## 22) Message formatting style update (2026-04-06)
- Файлы:
  - обновлен `app/bot/manager.py`.
- Поведение:
  - в pending/split сообщениях каждое предложение вынесено на новую строку;
  - выделенные подсказки (`ВАЖНО`) оформлены с пустой строкой до и после;
  - сервисные статусы отправки (`Собрано файлов...`, `Файл получен...`) также переведены на построчный формат.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`

## 23) Global message line-break style (2026-04-06)
- Файлы:
  - обновлены `app/bot/manager.py`, `app/utils/user_messages.py`.
- Поведение:
  - все основные пользовательские сообщения в боте переведены в формат «одно предложение = одна строка»;
  - в длинных уведомлениях и error-hints убраны склейки предложений через пробел, добавлены явные переносы;
  - формат применен не только к pending/split, но и к авторизации, ограничениям, ошибкам backend и подсказкам из `format_user_response`.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 24) Telegram button styles (Bot API 9.4) enabled (2026-04-06)
- Файлы:
  - обновлены `requirements.txt`, `app/bot/manager.py`.
- Поведение:
  - зависимость `aiogram` обновлена до `3.27.0` (поддержка `InlineKeyboardButton.style`);
  - для ключевых кнопок выставлены стили: `success`, `danger`, `primary`, `default`;
  - применено в pending/split/PDF/invoice-action/edit-action сценариях.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 25) Centralized bot texts file (2026-04-06)
- Файлы:
  - добавлен `app/bot/messages.py`;
  - обновлен `app/bot/manager.py` (переведен на `Msg.*` для пользовательских сообщений).
- Поведение:
  - основные пользовательские тексты бота вынесены в один файл для ручной правки «за один проход»;
  - в `manager.py` сообщения отправляются через константы из `messages.py`.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 26) Single text source for formatter + bot (2026-04-07)
- Файлы:
  - обновлены `app/bot/messages.py`, `app/bot/manager.py`, `app/utils/user_messages.py`.
- Поведение:
  - тексты из `format_user_response` и `format_invoice_markdown` вынесены в `app/bot/messages.py` (hints, статусы, подписи полей, шаблоны строк);
  - `manager.py` и `user_messages.py` используют единый источник `Msg.*`;
  - в `manager.py` больше нет прямых строк в `answer/edit_text/send_message`.
- Быстрая проверка:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 27) Full UI text centralization incl. button labels (2026-04-07)
- Files:
  - updated `app/bot/messages.py`, `app/bot/manager.py`.
- Behavior:
  - button captions, command description, merge aliases, request-code line, and invoice field labels are now read from `Msg.*`;
  - `manager.py` no longer keeps runtime user-facing text literals in `answer/edit_text/send_message/InlineKeyboardButton(text=...)`.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`

## 28) PDF mode UX simplification (2026-04-07)
- Files:
  - updated `app/bot/messages.py`, `app/bot/manager.py`, `tests/test_bot_stage5.py`.
- Behavior:
  - removed extra `Продолжить` button from PDF mode selection;
  - flow is now explicit: user selects `fast` or `accurate`, and processing starts immediately;
  - added user hint in PDF prompt: for unclear/low-quality document use `accurate`.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 -v`

## 29) PDF pending-state fix for mode buttons (2026-04-07)
- Files:
  - updated `app/bot/manager.py`, `tests/test_bot_stage5.py`.
- Behavior:
  - after uploading a PDF, user is explicitly registered in pending state before showing `fast/accurate` buttons;
  - callback handlers now restore pending state from saved pending files (covers bot restart between upload and button click);
  - added status logging for PDF no-pending and selected PDF mode.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 -v`

## 30) Worker stability hardening for long PDF jobs (2026-04-07)
- Files:
  - updated `app/config.py`, `app/entrypoints/worker.py`, `scripts/dev_run_all.py`.
- Behavior:
  - worker now uses configurable RQ timings via settings:
    - `WORKER_TTL_SEC` (default `1800`)
    - `WORKER_MAINTENANCE_INTERVAL_SEC` (default `60`)
    - `WORKER_JOB_MONITORING_INTERVAL_SEC` (default `15`)
  - `scripts/dev_run_all.py` now enforces single running instance via `tmp/dev_run_all.lock`, reducing accidental duplicate worker/backend/bot process trees.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 31) Not-invoice user text centralized (2026-04-07)
- Files:
  - updated `app/bot/messages.py`, `app/services/pipeline.py`.
- Behavior:
  - user-facing not-invoice phrases are now centralized in `Msg` (`NOT_INVOICE_HINT`, `NOT_INVOICE_MESSAGE`, `BATCH_NOT_INVOICE_MESSAGE`);
  - pipeline now reads those strings from `messages.py` instead of inline literals.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_invoice_recognition tests.test_user_messages -v`

## 32) Not-invoice phrase unified into one constant (2026-04-07)
- Files:
  - updated `app/bot/messages.py`, `app/services/pipeline.py`.
- Behavior:
  - detailed not-invoice user phrase is now a single constant `Msg.NOT_INVOICE_MESSAGE` (no concatenation from multiple parts);
  - pipeline uses this single constant directly.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_invoice_recognition tests.test_user_messages -v`

## 33) Removed hidden /mode commands logic (2026-04-07)
- Files:
  - updated `app/bot/manager.py`, `app/bot/messages.py`.
- Behavior:
  - removed command handlers for `/mode`, `/modefast`, `/modeaccurate`;
  - removed legacy message constants used only by those commands;
  - PDF mode selection remains only in inline flow after PDF upload (`fast/accurate`).
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 34) Batch wording for error/not-invoice messages (2026-04-07)
- Files:
  - updated `app/bot/messages.py`, `app/utils/user_messages.py`, `docs/TODO.md`.
- Behavior:
  - for multi-file/batch responses, generic error line is now plural (`Не получилось обработать файлы.`);
  - batch not-invoice message is now plural and uses `файлы/документы` wording;
  - TODO updated to reflect Stage 5 status and current PDF mode flow without `/mode`.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_user_messages tests.test_invoice_recognition tests.test_bot_stage5 -v`

## 35) Batch flag propagation fix in worker responses (2026-04-07)
- Files:
  - updated `app/tasks.py`, `tests/test_user_messages.py`.
- Behavior:
  - worker now always propagates `batch` flag into `result_payload` before user-message formatting;
  - plural error text (`Не получилось обработать файлы.`) is now reliably used for batch failures.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_user_messages tests.test_bot_stage5 -v`

## 36) Rollback of runtime lock guards for local start flow (2026-04-07)
- Files:
  - updated `app/entrypoints/bot.py`, `scripts/dev_run_all.py`.
- Behavior:
  - removed `bot.lock` single-instance guard from bot entrypoint;
  - removed `dev_run_all.lock` single-instance guard from launcher;
  - launch flow is back to process-based control (kill/restart strategy).
- Quick check:
  - `.venv\\Scripts\\python.exe -m py_compile app\\entrypoints\\bot.py scripts\\dev_run_all.py`

## 37) Pre-kill start strategy in dev runner (2026-04-07)
- Files:
  - updated `scripts/dev_run_all.py`.
- Behavior:
  - added mandatory pre-kill phase before start to terminate existing project runtime processes (`dev_run_all`, `uvicorn app.api`, `worker`, `bot`);
  - start command is now idempotent for local dev: each run begins from a clean process state.
- Quick check:
  - `.venv\\Scripts\\python.exe -m py_compile scripts\\dev_run_all.py`

## 38) Pre-kill self-termination fix in dev runner (2026-04-07)
- Files:
  - updated `scripts/dev_run_all.py`.
- Behavior:
  - pre-kill no longer targets `dev_run_all.py` processes;
  - only runtime services are terminated (`backend`, `worker`, `bot`), so launcher start from IDE no longer kills itself.
- Quick check:
  - `.venv\\Scripts\\python.exe -m py_compile scripts\\dev_run_all.py`

## 39) Batch not-invoice phrasing normalization (2026-04-07)
- Files:
  - updated `app/utils/user_messages.py`, `tests/test_user_messages.py`.
- Behavior:
  - in batch error responses, singular not-invoice message is auto-normalized to plural wording (`файлы`, `документах`);
  - prevents mixed output like `Не получилось обработать файлы` + `файл не содержит...`.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_user_messages tests.test_bot_stage5 -v`

## 40) Stage 6 kickoff: /status command for queue and last request (2026-04-08)
- Files:
  - updated `app/task_store.py`, `app/bot/manager.py`, `app/bot/messages.py`, `tests/test_bot_stage5.py`, `docs/TODO.md`.
- Behavior:
  - added `/status` command in bot menu and handler;
  - user now sees queue aggregates (`queued`/`processing`), pending draft file count, and last request status/message;
  - task store now exposes read helpers `get_queue_snapshot()` and `get_user_last_task(user_id)`.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 tests.test_user_messages -v`

## 41) /status UX switched to user-only active view (2026-04-08)
- Files:
  - updated `app/task_store.py`, `app/bot/manager.py`, `app/bot/messages.py`, `.env.example`, `tests/test_bot_stage5.py`.
- Behavior:
  - `/status` now shows only current user's active requests (no global queue of all users);
  - added active window + stale detection (`STATUS_ACTIVE_HOURS`, `STATUS_STALE_MINUTES`);
  - added inline refresh button in status message (`status:refresh` callback).
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 42) /status message reuse (no status spam) (2026-04-08)
- Files:
  - updated `app/bot/manager.py`, `tests/test_bot_stage5.py`.
- Behavior:
  - repeated `/status` now edits the previous status card instead of creating new messages;
  - if old status message is unavailable, bot sends a new one and stores it as current;
  - refresh callback keeps status-card pointer up to date.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_bot_stage5 -v`

## 43) Neutral recognition header for all document types (2026-04-08)
- Files:
  - updated `app/bot/messages.py`.
- Behavior:
  - final success header changed from `Распознанная накладная` to neutral `Документ распознан`;
  - avoids mismatched wording when source document is invoice/receipt/etc.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_user_messages tests.test_bot_stage5 -v`

## 44) /status: stale-task reaper + optional pinned card (2026-04-08)
- Files:
  - updated `app/task_store.py`, `app/bot/manager.py`, `app/bot/messages.py`, `app/config.py`, `.env.example`, `tests/test_bot_stage5.py`, `docs/TODO.md`.
- Behavior:
  - `/status` now auto-reaps stale `queued/processing` tasks to timeout error (configurable);
  - status card can be pinned (`STATUS_PIN_MESSAGE=true`) with safe fallback if chat permissions do not allow pinning;
  - retained no-spam behavior: one status card per user is edited/reused.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 45) /status retry action for last failed request (2026-04-08)
- Files:
  - updated `app/bot/manager.py`, `app/bot/messages.py`, `tests/test_bot_stage5.py`, `docs/TODO.md`.
- Behavior:
  - status card now shows `Повторить обработку` for the last failed request (if source payload exists);
  - retry callback resubmits original file/batch to backend and refreshes status card in-place;
  - access guard added: retry is blocked for requests of another user.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`

## 46) Stage 6: iiko import fallback via CSV/XLSX (2026-04-08)
- Files:
  - added `app/iiko/import_export.py`, `tests/test_iiko_import_export.py`;
  - updated `app/services/pipeline.py`, `app/config.py`, `app/schemas.py`, `app/bot/messages.py`, `app/bot/manager.py`, `app/utils/user_messages.py`, `tests/test_invoice_recognition.py`, `tests/test_user_messages.py`, `.env.example`, `docs/TODO.md`, `docs/README.md`, `docs/ARCHITECTURE.md`.
- Behavior:
  - if direct iiko upload via server API fails after retries, pipeline can return successful fallback with generated import file (`CSV` or `XLSX`) instead of hard error;
  - fallback behavior is configurable via `IIKO_IMPORT_FALLBACK_ENABLED`, `IIKO_IMPORT_FORMAT`, `IIKO_IMPORT_EXPORT_DIR`;
  - user-facing responses now indicate import-file fallback (`format_user_response` and invoice markdown), and manual `inv:send` treats fallback as non-failed outcome.
- Quick check:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_iiko_import_export tests.test_user_messages tests.test_invoice_recognition -v`

## 47) dev_run_all: module-based worker/bot startup (2026-04-08)
- Files:
  - updated `scripts/dev_run_all.py`, `docs/DEBUG.md`.
- Behavior:
  - `dev_run_all` now starts worker/bot as modules (`-m app.entrypoints.worker`, `-m app.entrypoints.bot`) instead of direct file execution;
  - prevents `ModuleNotFoundError: No module named 'app'` in local orchestration and aligns standalone runbook commands with runtime behavior.
- Quick check:
  - `.venv\\Scripts\\python.exe scripts\\dev_run_all.py`
  - `.venv\\Scripts\\python.exe scripts\\dev_status.py`

## 50) iiko API contract confirmed from PDF + /article pages (2026-04-18)
- Files:
  - updated `app/iiko/server_client.py`, `app/config.py`, `.env.example`, `docs/IIKO_API_GAPS.md`, `iiko_server_docs/README.md`, `iiko_server_docs/INDEX.md`;
  - added `tests/test_iiko_server_client.py`.
- Behavior:
  - auth now follows official iikoServer contract: `POST /resto/api/auth?login=...&pass=<sha1(password)>`;
  - upload now targets `POST /resto/api/documents/import/incomingInvoice?key=...` with XML payload;
  - token is used as query param and cookie `key`;
  - API mode now requires product mapping fields in `InvoiceItem.extras` (`product`/`supplierProduct`/`supplierProductArticle`), otherwise direct upload is skipped with explicit error and fallback path remains available.
- Verification source:
  - `C:\\Users\\MiBookPro\\Downloads\\iikoserver-api.pdf`;
  - `https://ru.iiko.help/article/api-documentations/avtorizatsiya`;
  - `https://ru.iiko.help/article/api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy`;
  - `https://ru.iiko.help/article/api-documentations/opisanie-oshibok`.

## 51) Demo stand CRMID 8950663 integrated into local env (2026-04-18)
- Files:
  - added `docs/IIKO_DEMO_STAND.md` (sanitized stand metadata + links);
  - added `data/private/iiko_demo_stand_8950663.md` (full letter with access details, local only);
  - updated local `.env` to new API transport keys:
    - `IIKO_API_BASE_URL=https://840-786-070.iiko.it`
    - `IIKO_API_AUTH_PATH=/resto/api/auth`
    - `IIKO_API_UPLOAD_PATH=/resto/api/documents/import/incomingInvoice`
    - `IIKO_USERNAME=user`
    - `IIKO_PASSWORD=<from letter>`
- Notes:
  - `IIKO_TRANSPORT` intentionally left as `import_only` for safe default;
  - switching to direct API mode requires mapped iiko identifiers in `InvoiceItem.extras`.

## 52) Live smoke on demo stand: auth OK, import requires payload hardening (2026-04-18)
- Files:
  - updated `app/iiko/server_client.py`, `docs/IIKO_API_GAPS.md`.
- Behavior:
  - auth now tries `form-urlencoded` first (compatible with 9.4 demo stand), then query fallback;
  - live check confirmed `auth_status=200` on `https://840-786-070.iiko.it/resto/api/auth` with `login=user`, `pass=sha1(user#test)`;
  - live check to `incomingInvoice` confirmed endpoint availability but returned `500 NPE` for minimal synthetic XML, indicating payload/business mapping is still incomplete.
- Operational note:
  - shell-level env vars `IIKO_USERNAME/IIKO_PASSWORD` can override `.env`; when debugging, verify effective values in process.

## 53) iiko incomingInvoice made production-usable on demo stand (2026-04-18)
- Files:
  - updated `app/iiko/server_client.py`, `app/config.py`, `.env.example`, `app/iiko/README.md`, `tests/test_iiko_server_client.py`, `docs/IIKO_API_GAPS.md`.
- Behavior:
  - added catalog auto-resolve (`IIKO_AUTORESOLVE_PRODUCTS=true`):
    - pulls `/resto/api/v2/entities/products/list`;
    - resolves row mapping by `productArticle/article/num`, then `code`, then `name`;
    - writes mapped `product` + `productArticle` + optional `code` into item extras;
  - added optional store auto-fill (`IIKO_AUTOFILL_STORE=true`) from `/resto/api/corporation/stores` when exactly one store is available;
  - added cache control for catalog lookup (`IIKO_CATALOG_CACHE_SEC`, default `300`);
  - added required document-level metadata for import XML:
    - `documentNumber`, `incomingDocumentNumber`, `dateIncoming`, `useDefaultDocumentTime`, `defaultStore` (when single store).
- Live verification:
  - before metadata: minimal payload consistently returned `500 NPE`;
  - after metadata + mapping: direct `upload_invoice_items(...)` returns success (`documentValidationResult.valid=true`) on CRMID `8950663`.

## 54) iiko incomingInvoice posting and stock verification (2026-04-18)
- Files:
  - updated `app/iiko/server_client.py`, `app/services/pipeline.py`, `app/schemas.py`, `app/config.py`, `.env.example`, `tests/test_iiko_server_client.py`, `docs/IIKO_API_GAPS.md`, `docs/TODO.md`.
- Business finding:
  - `documentValidationResult.valid=true` only proves that iiko accepted the XML;
  - exported document `status=NEW` means draft/not posted;
  - exported document `status=PROCESSED` plus `/resto/api/v2/reports/balance/stores` delta proves warehouse receipt for stock-moving goods.
- Live demo proof on CRMID `8950663`:
  - demo catalog initially had only `SERVICE` items, so previous smoke did not prove stock movement;
  - created one API test `GOODS` product with `products/save`;
  - import with `status=PROCESSED` requires `supplier`;
  - updated client path created `bot-20260418235937-672c5b`, export returned `PROCESSED`, stock delta was `amount_delta=1`, `sum_delta=5`.
- Runtime knobs:
  - `IIKO_INCOMING_INVOICE_STATUS=NEW` creates a draft for manual review;
  - `IIKO_INCOMING_INVOICE_STATUS=PROCESSED` attempts real posting;
  - `IIKO_DEFAULT_SUPPLIER_ID` is needed for posting if supplier is not mapped from document extras;
  - `IIKO_VERIFY_UPLOAD=true` verifies via export by number;
  - `IIKO_VERIFY_STOCK_BALANCE=true` verifies before/after balance delta for resolved `product + store` pairs.

---

### Быстрый чек-лист для нового агента
1) Прочитать этот файл.
2) Открыть `pipeline.py`, найти настройки LLM (max_output_tokens/maxItems) и детектор мусора.
3) При любой проблеме — взять код заявки и запустить `scripts/diagnose_request.py`.
