# TODO / План работ (декомпозиция)

## Этап 1 — Минимальные изменения, высокая стабильность
- [x] Feature flags: добавить конфиг-флаги в `.env` и загрузку в `app/config.py`
- [x] Feature flags: использовать флаги в `pipeline.py` (LLM fallback, split логика)
- [x] Mailbox-лог: расширить `logs/requests/users/*.jsonl` событиями статусов
- [x] TTL-cleanup: очистка `data/pending` и `data/split` по времени
- [x] Лимиты: базовые ограничения размера/частоты файлов на пользователя
- [x] Идемпотентность: защита от повторной обработки одного и того же файла

## Этап 2 — Масштабируемость 1000+
- [x] Перевод бота на webhook
- [x] Очередь задач: Redis + RQ/Celery (выбрать стек)
- [x] Воркеры: вынести LLM обработку
- [x] Воркеры: вынести загрузку в iiko (ограничить параллелизм)
- [x] Хранилище задач: SQLite/Postgres (выбрать и подключить)

## Этап 3 — Оптимизация затрат и качество распознавания
- [x] Branch status: feature/todo-stage3-guardrails-ux scope completed (guardrails + OCR quality); remaining stage-3 parser tasks moved to next-stage backlog.
- [ ] Типовые формы: распознавание ТОРГ-12, УПД, 1-Т
- [ ] Гибрид: быстрый парсер → fallback в LLM
- [ ] Метрики стоимости: агрегаты по дню/пользователю
- [x] LLM-guardrails: детектор «мусорных» ответов (повторы, нулевые строки, стоп-слова)
- [x] UX ошибок распознавания: единый формат сообщений (`user_messages.py`) + подсказки «что сделать иначе» (PDF/цельное фото, /split)
- [x] `_append_cost_log`: логирование стоимости LLM для всех исходов (не только успешных)
- [x] `_append_cost_log`: переписан на append-only (без перечтения всего CSV)
- [x] `.env` / BOM: `env_file_encoding="utf-8-sig"` + скрипт `scripts/strip_bom.py`

## Этап 4 — Надежность и наблюдаемость
- [x] Централизованные логи + алерты
- [x] Ротация и архивирование логов
- [x] Мониторинг ошибок и времени обработки
- [x] Коды событий бота (`BOT_BACKEND_UNAVAILABLE`, `BOT_PENDING_TIMEOUT`, …) — собрать и описать в одном месте
- [x] DEBUG.md: проверенный runbook по запуску/остановке/логам для backend/worker/bot
- [x] Dev-оркестрация: `scripts/dev_run_all.py` с авто-киллом дублей бота
- [x] Dev-оркестрация: довести `DEV_SETUP.md` до статуса «повторяемый сценарий для нового разработчика»
- [x] Удалить мёртвую папку `app/logs/` (все логи пишутся в корневую `logs/`)

## Этап 5 — UX бота (незавершённые пункты из feature/ui-messages)
- [x] `/split` + `/done` + `/cancel` кнопки; идемпотентность `/done`
- [x] `/mode` с inline-кнопками fast/accurate
- [x] Pending: убран скрытый 5с таймер, заменён на явный UI с кнопками «▶️ Обработать / 📎 Добавить ещё»
- [x] Агрегация альбома в split-режиме: одно сообщение «Добавлено N фото» вместо N отдельных
- [ ] Доработать дедупликацию файлов (сейчас жёсткая проверка убрана, нужна мягкая)
- [ ] Fixtures для smoke-тестов (папка `fixtures/` с контрольными файлы)

## Этап 6 — Выявлено из dialogue_dump (Copilot-сессия)
- [x] Переход Tesseract → OpenAI LLM (function calling parse_invoice)
- [x] PDF через Files API (file_id) — решило 400 Bad Request
- [x] PDF image fallback (рендер страниц + разрез пополам) — решило пропуск строк
- [x] Авторизация iiko через бота (/start → login → password → users.json)
- [x] Cost logging: llm_costs.csv + llm_usage в JSON запросов
- [x] Docker: deploy/Dockerfile + deploy/docker-compose.yml (backend, worker, bot, redis)
- [ ] HTTPS + webhook на VPS (домен + Let's Encrypt + Nginx)
- [ ] iiko: маппинг позиций → импорт через CSV/XLSX (альтернатива Playwright)
- [ ] Быстрый парсер ТОРГ-12 / УПД без LLM (экономия на типовых формах)
- [ ] Команда /status (показ состояния очереди задач пользователю)
- [ ] Auto-restart воркера и backend (systemd / docker restart policy)

## Этап 7 — Альтернативный LLM-провайдер (Cloudflare + Gemini)
> Отдельная ветка / feature flag. Не блокирует основной трек.
- [ ] Cloudflare Worker как прокси к Gemini API
- [ ] Python-клиент: переключение провайдера через `.env` (`LLM_PROVIDER=openai|gemini`)
- [ ] Кнопка/команда в боте для переключения провайдера на лету
- [ ] Маппинг function calling OpenAI ↔ Gemini (единый интерфейс)
- [ ] Сравнительный A/B: логирование качества/стоимости по провайдерам

## Stage 8 — iikoServer import readiness (2026-03-11)
- [x] Collected and verified iikoServer incoming/outgoing invoice endpoint specs from `ru.iiko.help`.
- [x] Prepared full field mapping and posting strategy doc: `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`.
- [x] Prepared business integration roadmap doc: `docs/exp/BUSINESS_INTEGRATIONS_PLAN.md`.
- [x] Captured current iiko Store/Connectors snapshot: `docs/exp/IIKO_STORE_CATALOG.md`.
- [x] Implement `iikoServer` auth/session client in app service layer.
- [x] Implement `InvoiceItem -> incomingInvoiceItemDto` mapper with unit/pack conversion.
- [x] Add idempotency guard by external document key and duplicate prevention policy.
- [x] Add dual-path feature flag (`iikoServer` primary, Playwright fallback).

## Stage 8.1 — RMS demo stand onboarding (2026-03-16)
- [x] Formalized RMS demo profile and links in doc: `docs/exp/IIKO_RMS_DEMO_PROFILE_2026-03-16.md`.
- [ ] Define secure secrets policy for demo credentials (no plaintext in tracked docs for non-demo environments).
- [ ] Add smoke auth/health script for RMS REST endpoint and expected response checks.
- [ ] Run first end-to-end import test against demo stand and record findings in `docs/DEBUG.md`.

## Риски (архитектура и надежность)
- [x] `P0` Batch flow: исправить обработку `files[]` в worker (`app/tasks.py`), чтобы батч не деградировал до `files[0]`; добавить регрессионный тест.
- [x] `P1` Queue timeout: задать явный `job_timeout`/retry policy для разных типов задач (`single`, `batch`, `iiko upload`), добавить обработку failed jobs.
- [ ] `P1` Throughput: подготовить профиль горизонтального масштабирования worker + мониторинг глубины очереди/lag.
- [ ] `P1` Stateful bot: вынести runtime-state бота из памяти в персистентное хранилище для безопасного restart/horizontal scale.
- [ ] `P1` Secrets: убрать хранение iiko credentials в `data/users.json`, перевести на защищенное хранилище с контролем доступа.

