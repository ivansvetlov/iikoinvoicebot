# TODO / План работ (декомпозиция)

## Текущий статус (2026-06-17)

- **Активная ветка:** `feature/stage6-iiko-import-readiness-kickoff`.
- **Фокус:** основная линия stage6 (iiko demo stand + post-recognition UX E2E).
- **Демо-стенд:** API снова доступен (`IIKO_AUTH_OK`, см. `docs/iiko/IIKO_DEMO_STAND.md`).
- **Следующий шаг:** dry-run/cleanup склада → `dev_run_all` → ручной прогон `docs/iiko/INVOICE_FLOW_TESTING.md`.

## Отложено: Telegram «Избранное» (research track)

**Статус: пауза** (2026-06-17). Не блокирует stage6, не смешивать в коммиты спринта.

- Скрипт готов: `scripts/export_telegram_saved.py` → `data/private/telegram_favorites/`.
- Блокер: `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` (my.telegram.org — «попробуйте позже»).
- Обходной путь на возобновление: экспорт Telegram Desktop → `data/private/telegram_favorites/desktop_export/`.
- Целевой deliverable: 4-секционный отчёт (raw extract, link map, utility matrix, roadmap) в отдельной ветке `exp/topic-pipeline-toolkit-research`.
- Детали: `docs/governance/DEFERRED_BRANCH_NOTES.md` (раздел «Telegram favorites research»).

Детальный post-audit трек: `docs/governance/AUDIT_REMEDIATION_PLAN.md` (не дублировать чеклисты здесь).

## Post-audit remediation (summary)

Источник: `docs/governance/COMPREHENSIVE_AUDIT.md` → трек: `docs/governance/AUDIT_REMEDIATION_PLAN.md`.

- [x] Governance baseline: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, PR template
- [x] `docs/governance/PROJECT_CLONE_PROMPT.md` (skeleton blueprint)
- [x] Ignore `dump stage*` / `last chat` в `.gitignore`
- [x] `COMPREHENSIVE_AUDIT.md` → `docs/`
- [ ] CI: tests + lint на push/PR
- [ ] Branch protection на main
- [ ] `requirements-dev.txt` + pre-commit
- [ ] Документировать `prompts/` в `docs/README.md`
- [ ] Удалить локальный `dump stage6`

## Этап 6 kickoff — post-recognition UX и iiko import (текущий спринт)

### Сделано локально (нужен коммит)
- [x] Клавиатуры post-recognition: `app/bot/invoice_keyboards.py`
- [x] Проверка готовности строк: `app/bot/invoice_posting.py`
- [x] Callback-flow в `manager.py`: редактировать → синхронизировать → оприходовать → сервис → назад
- [x] Экран review перед оприходованием (`inv:send` → posting review → `inv:postconfirm`)
- [x] Sync nomenclature: confirm → `/iiko-sync-nomenclature`
- [x] Worker отдаёт те же кнопки после распознавания (`tasks.py`)
- [x] `user_store`: профили категорий + global category bank
- [x] `resolver` + `unit_conversion`: owner rules, density, LLM fallback (тесты `test_invoice_flow_conversion.py`)

### Осталось в этом спринте
- [ ] Закоммитить и запушить post-recognition UX + тесты
- [ ] Ручной прогон по `docs/iiko/INVOICE_FLOW_TESTING.md` на demo stand
- [ ] Подключить `INVOICE_FLOW_MODE=modular` в production pipeline (сейчас runner standalone)
- [ ] НДС: парсинг из колонки «Сумма», не «Сумма с НДС»; строки «В том числе НДС» (заявка 83565)
- [ ] Убрать дубли сообщений при переходе к posting review (worker + bot race)
- [ ] Сервисное меню: реализовать rollback/clear-stock (сейчас заглушки)
- [ ] E2E scaffold: довести `tests/test_e2e_invoice_posting.py` или пометить `@pytest.mark.e2e` + skip без env
- [ ] Решение по iiko posting policy: `NEW` draft vs `PROCESSED` auto-post

### Из планов Codex (отдельные ветки / следующие слои)

См. также `docs/planning/BRANCH_WAIT_OPTIMIZATION_PLAN.md`, `docs/planning/MENU_DOMAIN_EXPANSION_PLAN.md`, `docs/governance/DEFERRED_BRANCH_NOTES.md`.

#### Invoice flow / единицы измерения
- [ ] `data/invoice_flow_owner_rules.json` — заполнить правила для реальных SKU клиента
- [ ] Подключить `prompts/invoice_unit_resolution_fork.txt` в dev/staging
- [ ] Метрики: `flowConversionReason`, retry count, cost delta (см. `DEFERRED_BRANCH_NOTES`)

#### Оптимизация ожидания распознавания (`BRANCH_WAIT_OPTIMIZATION_PLAN`)
- [ ] Ветка: bounded LLM retry budget (max calls / max truncation retries)
- [ ] Dynamic initial `max_output_tokens` по сложности документа
- [ ] Метрики p95 latency до/после

#### Категории и меню (`MENU_DOMAIN_EXPANSION_PLAN`)
- [ ] Подключить `category_onboarding.py` в первый запуск бота
- [ ] UX: optional-шаг «введите свои категории»
- [ ] `tenant_category_map` (сейчас только `global_category_bank` в `user_store`)
- [ ] UX: ручной выбор категории по позиции
- [ ] `product_type_classifier`: INGREDIENT / SEMI_FINISHED / DISH
- [ ] Discovery endpoint'ов техкарт перед `techcard_linker`

## Текущий фокус MVP (апрель 2026)
- [ ] Не расширять production-сценарии за пределы текущего MVP до закрытия Этапов 3/4/6
- [ ] Довести стабильный контур: распознавание → валидация → выгрузка в учетную систему
- [ ] Зафиксировать базовый SLA MVP (время обработки, доля успешных распознаваний, доля ручных доработок)

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
- [x] Stage status: закрыт по MVP scope (2026-04-06)
- [x] Типовые формы: распознавание ТОРГ-12, УПД, 1-Т
- [x] LLM-guardrails: детектор «мусорных» ответов (повторы, нулевые строки, стоп-слова)
- [x] UX ошибок распознавания: единый формат сообщений (`user_messages.py`) + подсказки «что сделать иначе» (PDF/цельное фото, /split)
- [x] Диагностика качества распознавания: image-level debug (`scripts/diagnose_image.py` + `tmp/llm_debug/*`)
- [x] `_append_cost_log`: логирование стоимости LLM для всех исходов (не только успешных)
- [x] `_append_cost_log`: переписан на append-only (без перечтения всего CSV)
- [x] `.env` / BOM: `env_file_encoding="utf-8-sig"` + скрипт `scripts/strip_bom.py`

## Этап 4 — Надежность и наблюдаемость
- [x] Централизованные логи + алерты
- [x] Ротация и архивирование логов
- [x] Мониторинг ошибок и времени обработки
- [x] Коды событий бота (`BOT_BACKEND_UNAVAILABLE`, `BOT_PENDING_TIMEOUT`, …) — собрать и описать в одном месте
- [x] DEBUG.md: проверенный runbook по запуску/остановке/логам для backend/worker/bot
- [x] Dev-оркестрация: `scripts/dev_run_all.py` (lock + pre-kill всего стека, `--force` / `--reuse-backend`)
- [x] Dev-оркестрация: довести `DEV_SETUP.md` до статуса «повторяемый сценарий для нового разработчика»
- [x] Удалить мёртвую папку `app/logs/` (все логи пишутся в корневую `logs/`)

## Этап 5 — UX бота (незавершённые пункты из feature/ui-messages)
- [x] Stage status: закрыт по текущему UX/MVP scope (2026-04-07)
- [x] `/split` + `/done` + `/cancel` кнопки; идемпотентность `/done`
- [x] Выбор режима PDF (`fast`/`accurate`) в inline-потоке после отправки PDF (без отдельной команды `/mode`)
- [x] Pending: убран скрытый 5с таймер, заменён на явный UI с кнопками «▶️ Обработать / 📎 Добавить ещё»
- [x] Агрегация альбома в split-режиме: одно сообщение «Добавлено N фото» вместо N отдельных
- [x] Доработать дедупликацию файлов (сейчас жёсткая проверка убрана, нужна мягкая)
- [x] Fixtures для smoke-тестов (папка `fixtures/` с контрольными файлами)

## Этап 6 — Выявлено из dialogue_dump (Copilot-сессия)
- [x] Переход Tesseract → OpenAI LLM (function calling parse_invoice)
- [x] PDF через Files API (file_id) — решило 400 Bad Request
- [x] PDF image fallback (рендер страниц + разрез пополам) — решило пропуск строк
- [x] Авторизация iiko через бота (/start → login → password → users.json)
- [x] Cost logging: llm_costs.csv + llm_usage в JSON запросов
- [x] Docker: Dockerfile + docker-compose.yml (backend, worker, bot, redis)
- [ ] HTTPS + webhook на VPS (домен + Let's Encrypt + Nginx)
- [x] iiko: маппинг позиций → импорт через CSV/XLSX (альтернатива прямой API-выгрузке)
- [ ] Быстрый парсер ТОРГ-12 / УПД без LLM (экономия на типовых формах)
- [x] Команда /status (показ состояния очереди задач пользователю)
- [x] /status: user-only view + auto-reap зависших queued/processing
- [x] /status: одна обновляемая карточка (без спама) + закрепление (pin) по настройке
- [x] /status: retry из карточки для последней ошибочной заявки
- [ ] Auto-restart воркера и backend (systemd / docker restart policy)

## Этап 7 — Альтернативный LLM-провайдер (Cloudflare + Gemini)
> Отдельная ветка / feature flag. Не блокирует основной трек.
- [ ] Cloudflare Worker как прокси к Gemini API
- [ ] Python-клиент: переключение провайдера через `.env` (`LLM_PROVIDER=openai|gemini`)
- [ ] Кнопка/команда в боте для переключения провайдера на лету
- [ ] Маппинг function calling OpenAI ↔ Gemini (единый интерфейс)
- [ ] Сравнительный A/B: логирование качества/стоимости по провайдерам

## Этап 8 — Каналы продаж и омниканальный intake (B2B)
- [ ] MAX: проверить продакшен-готовность API/ботов и ограничения для бизнес-сценария
- [ ] MAX: MVP-канал «получить документ → распознать → вернуть результат + статус»
- [ ] Telegram+MAX: единый backend для multi-channel без дублирования бизнес-логики
- [ ] Очереди/лимиты по каналам: отдельные rate limits и SLA-приоритеты
- [ ] Единая воронка конверсии: trial → платный тариф по каналам

## Этап 9 — Интеграции учета и операционных систем как core-value
- [ ] МойСклад: двусторонняя интеграция (создание приходных документов + справочники номенклатуры)
- [ ] 1С: вариант интеграции (HTTP-сервис/обмен файлами) + спецификация маппинга полей
- [ ] iiko: production-ready коннектор (приход, справочники, статусы)
- [ ] r_keeper + StoreHouse: коннектор для учета и закупочных сценариев HoReCa
- [ ] Единый слой `connectors/`: iiko + r_keeper/StoreHouse + МойСклад + 1С с общим контрактом ошибок/ретраев
- [ ] Идемпотентный экспорт: защита от дублей при повторной отправке документов
- [ ] Нормализация справочников: единицы измерения, НДС, контрагенты, коды товаров
- [ ] Приоритет следующего шага: MAX + МойСклад + 1С (как базовый контур для РФ-сегмента)

## Этап 10 — Коммерциализация и удержание
- [ ] Продуктовые пакеты: Starter / Pro / Enterprise (лимиты документов, SLA, интеграции)
- [ ] ROI-дашборд для клиента: сэкономленные часы, точность, стоимость обработки 1 документа
- [ ] Onboarding ≤ 1 день: шаблоны отраслей (HoReCa, retail, дистрибуция)
- [ ] Partner motion: интеграторы 1С/МойСклад и франчайзи iiko как канал продаж
- [ ] Контур безопасности: аудит-доступы, журнал действий, политика хранения документов

## Этап 11 — Процессное масштабирование (cross-vertical modeling)
- [ ] Построить библиотеку типовых бизнес-процессов (BPM-шаблоны) для массовых SMB-сценариев
- [ ] Классификатор сценариев: отрасль × роль × событие × требуемая интеграция
- [ ] Унифицировать процессные цепочки: «потребность → заявка → заказ → приход → списание/учет»
- [ ] Voice-to-Order как один из каналов входа, а не отдельный продуктовый трек
- [ ] Нишевые шаблоны для пилота: beauty, retail, service teams (не только HoReCa)
- [ ] Ограничения и контроль в шаблонах: бюджеты, согласование, SLA, аудит действий
- [ ] Отдельная ветка для эксперимента: `feature/process-modeling`

## Этап 12 — Post-stage3 optimization backlog
- [x] Гибрид: быстрый парсер → fallback в LLM
- [x] Метрики стоимости: агрегаты по дню/пользователю

## Аудит веток и экспериментов (2026-04-05)
- [x] Проверено: ветка под текущий трек распознавания существует (`feature/recognition-improvements`)
- [x] Проверено: ветка под Excel/шаблоны существует (`feature/excel-support`)
- [x] Проверено: ветка под готовность импорта iiko существует (`feature/stage6-iiko-import-readiness`)
- [x] Проверено: ветки инфраструктурных экспериментов существуют (`feature/infra-termux-vibe-mcp`, `experiment/wvibe-light-shell`, `experiment/vibe-mcp-link`)
- [x] Создать ветку под канал MAX (`feature/channel-max`)
- [x] Создать ветку под интеграцию МойСклад (`feature/integration-moysklad`)
- [x] Создать ветку под интеграцию 1С (`feature/integration-1c`)
## Update 2026-04-18
- [x] iiko: direct `incomingInvoice` API stabilized on demo stand (auto product resolve + required document metadata)
- [x] iiko: verified the real posting path (`status=PROCESSED`) on demo stand with a `GOODS` item and `/reports/balance/stores` stock delta
- [x] iiko: client now returns document number/status and distinguishes draft creation from warehouse receipt
- [ ] iiko: product UX decision for production posting flow (`NEW` draft for review vs `PROCESSED` auto-post after confidence/mapping checks)
- [ ] iiko: supplier mapping policy (from document/vendor catalog/default supplier) before enabling auto-posting for real clients

## Update 2026-04-21
- [x] iiko: one-time E2E stock cleanup on demo stand completed (all non-zero balances reduced to 0)
- [x] iiko: added reusable stock reset utility `scripts/iiko_reset_stock.py` (dry-run + apply)
- [x] iiko: first-fill path improved with optional auto-create missing products (`IIKO_AUTOCREATE_PRODUCTS`)
- [x] iiko: verified incoming invoice posting from saved recognized request on clean stand (`status=PROCESSED`)
- [ ] iiko: decide default policy for auto-create in production (off by default vs selective allow-list)
