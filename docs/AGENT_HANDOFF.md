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
- Текущая работа по сообщениям/коротким кодам: ветка `feature/ui-messages`.

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
  - статусы и новые этапы (MAX, МойСклад, 1С, коммерциализация) добавлены в `docs/_md/root/TODO.md`.

## 11) Roadmap refocus (2026-04-06)
- В `docs/_md/root/TODO.md` уточнён приоритет: масштабирование через процессные модели (`cross-vertical modeling`), а не через набор разрозненных фич.
- Voice-сценарии зафиксированы как канал входа в унифицированный процессный конвейер, а не отдельный продукт.
- В интеграционном треке добавлен явный контур `iiko + r_keeper/StoreHouse + МойСклад + 1С` с приоритетом для РФ-сегмента: `MAX + МойСклад + 1С`.

## 12) Stage 3 final closure (2026-04-06)
- Stage 3 в `docs/_md/root/TODO.md` помечен как закрытый по MVP scope.
- Невыполненные ранее пункты Stage 3 (`гибридный парсер`, `метрики стоимости`) перенесены в `Этап 12 — Post-stage3 optimization backlog`.

## 13) Post-stage3 backlog execution (2026-04-06)
- В `pipeline.py` добавлен гибридный контур: быстрый `InvoiceParser` для `text/docx/pdf/excel` и fallback в LLM при неуспехе fast-path.
- Cost summary (`logs/llm_costs_summary.json`) расширен агрегатами `by_day` и `by_user`; обновлён `scripts/llm_costs_rebuild.py`.
- Для новых сценариев добавлены тесты в `tests/test_invoice_recognition.py` (fast-parser path + cost summary aggregates).

---

### Быстрый чек-лист для нового агента
1) Прочитать этот файл.
2) Открыть `pipeline.py`, найти настройки LLM (max_output_tokens/maxItems) и детектор мусора.
3) При любой проблеме — взять код заявки и запустить `scripts/diagnose_request.py`.
