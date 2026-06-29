# Distributed agents — архитектурный анализ

> **STATUS: PAUSED** (2026-06-22) — нет прод-сервера; C2/C5 отложены.
> Промпт-задание: `docs/governance/AGENT_PRIME.md`. Детали паузы: `docs/governance/DEFERRED_BRANCH_NOTES.md`.

**Дата анализа:** 2026-06-21
**Цель:** Подготовить основу для устранения критических проблем распределённой работы (локальный IDE/Cursor агент + серверный + Grok bridges по TG/MAX) без потери обратной совместимости.
**Основано на:** Полном сканировании кодовой базы, чтении ключевых модулей, grep по зависимостям.

## 1. Карта зависимостей и компонентов

### 1.1 Redis / RQ (очередь задач)
- **Использование:**
  - `app/queue.py`: `get_redis()`, `get_queue()` (rq.Queue)
  - `app/entrypoints/worker.py`: `SimpleWorker` на очереди (RQ)
  - `app/api.py`: `get_queue().enqueue(process_invoice_task, ...)` для `/process` и `/process-batch`
  - `docker-compose.yml`: сервис `redis:7-alpine`
  - `app/config.py`: `redis_url`, `queue_name`, worker_* timeouts
  - `requirements.txt`: `redis==5.0.7`
  - `scripts/dev_status.py`, observability и тесты косвенно используют.
- **Где НЕ используется:**
  - Нет хранения состояния задач (только очередь jobs).
  - Нет pub/sub, locks для координации между инстансами.
  - Нет в grok bridges (кроме упоминаний в доках).
- **Вывод:** Redis присутствует, но используется узко — только как брокер очереди RQ. Отлично подходит для расширения на state, но добавит зависимость.

### 1.2 Git (синхронизация и handoff)
- **Использование в ядре:**
  - Минимально. Файловая система (`data/jobs/`, `data/pending/`, SQLite `data/app.db`).
- **Тяжёлое использование в экспериментальных "агентах":**
  - `experiments/grok_telegram_bridge/git_snapshot.py`, `work_journal.py`
  - `experiments/grok_max_bridge/` (импортирует snapshot)
  - `data/private/grok_bridge/` и `grok_max_bridge/`: `runs/<id>/git_diff.patch`, `HANDOFF_LATEST.md`, `journal.jsonl`, `sessions.json`
  - `scripts/git.ps1`
  - Механизм "road (TG/MAX) ↔ home (Cursor)" для удалённого агента.
- **Проблемы (по контексту промпта):**
  - Медленно для частой синхронизации.
  - Конфликты, ручная работа с патчами.
  - Не решает потерю состояния задач в основном приложении.
- **Вывод:** Git — отличный инструмент для handoff агентов, но плох как единственное хранилище состояния.

### 1.3 Telegram бот
- **Реализация:**
  - `app/entrypoints/bot.py`: polling entrypoint → `TelegramBotManager`
  - `app/bot/manager.py`: aiogram `Bot` + `Dispatcher`, handlers, in-memory state (`_auth_state`, `_edit_state`, `_pending_*`, `_rate_limits` и т.д.)
  - `app/api.py`:
    - `setup_webhook()` (on startup если `USE_WEBHOOK`)
    - `POST /telegram/webhook` → валидация секрета → `manager.dp.feed_update(...)`
  - `app/config.py`: `use_webhook`, `webhook_url`, `webhook_secret`
  - `scripts/set_mode.ps1`, `docs/README.md`, `nginx_bot.conf`
- **Режимы:** Polling (локалка) и Webhook (прод).
- **Проблема гонки:** Telegram разрешает либо активный polling (`getUpdates`), либо webhook. При переключении/рестарте/много инстансов — конфликт. Нет graceful delete/setWebhook.

### 1.4 Max бот (канал MAX)
- **Реализация:** Полностью отдельная.
  - `experiments/grok_max_bridge/bot.py`: использует `maxapi` (не aiogram), свой `GrokMaxBridgeBot`, polling.
  - Отдельные конфиги, сессии, handoff: `data/private/grok_max_bridge/`
  - Нет webhook (вызывает delete_webhook).
  - Импортирует общие модули из `grok_telegram_bridge` (formatter, runner и т.д.).
- **Вывод:** Дублирование логики мостов. Отдельный "протокол".

### 1.5 Конфиги и инфраструктура
- `app/config.py`: Pydantic `Settings`, `.env` (utf-8-sig), все ENV (токены, redis, db, iiko, openai, лимиты, webhook).
- `docker-compose.yml`: redis + postgres + backend + worker + bot.
- `app/db.py`: SQLAlchemy, поддержка sqlite (default) / postgres.
- Отдельные `experiments/*/config.py` для bridges.
- `.env.example`, `nginx_bot.conf`, `Dockerfile`.

### 1.6 Хранение состояния задач
- **DB (основное):** `app/task_store.py` + `app/models.py:TaskRecord` (request_id, status, user_id, result_json и т.д.).
  - CRUD: `create_task`, `mark_processing/done/error`.
  - Используется в `api.py`, `tasks.py`, `bot/manager.py`.
- **In-memory (бот):** Много `dict` в `TelegramBotManager` (auth, pending files, edit state, media groups, rate limits). Теряются при перезапуске бота.
- **Файлы:** `data/jobs/<request_id>/payload.json` + изображения.
- **Вывод:** Нет единого распределённого состояния. При failover worker/backend — задачи в "queued" могут "зависнуть" или дублироваться. TaskStore не использует Redis.

### 1.7 Тесты
- `tests/`: ~20 файлов.
  - `test_grok_bridge.py`, `test_grok_max_bridge.py`
  - `test_worker_facts.py`, `test_task_*` нет прямого, но `test_e2e_invoice_posting.py`
  - Много unit по pipeline, user_store, invoice_flow.
- Нет тестов failover, webhook switching, распределённого состояния.
- `scripts/dev_status.py` для проверки runtime.

### 1.8 Другие
- Grok bridges (экспериментальные агенты): отдельная экосистема для "удалённого терминала" (grok -p + rules + handoff).
- Наблюдаемость: `app/observability.py`, логи, метрики, alerts.
- Нет централизованного мониторинга graceful shutdown в проде (кроме dev_run_all).

## 2. Точки входа для изменений (рекомендации)

1. **Единое состояние (C1):**
   - Слой: `app/task_store.py` + фабрика бэкендов.
   - Вход: `create_task` / marks + `app/tasks.py` (worker) + `app/api.py`.
   - Также: сделать state в manager pluggable или вынести в отдельный store.

2. **Webhook и переключение режимов (C2):**
   - `app/api.py` (setup_webhook, webhook handler, bot_manager singleton).
   - `app/bot/manager.py` (run polling).
   - `scripts/set_mode.ps1`, `app/config.py`.
   - Добавить идемпотентность + distributed lock.

3. **NAT / локалка (C5):**
   - Мосты (grok bridges) + dev_run_all уже решают частично (локальный агент).
   - Для прод: webhook + reverse proxy (уже есть nginx).
   - Добавить health + readiness для failover.

4. **Очередь задач:**
   - `app/queue.py` (текущий абстракция хорошая).
   - Можно расширить (Redis streams, или Celery как альтернатива).

5. **Grok bridges (распределённые агенты):**
   - `experiments/grok_*_bridge/` + `data/private/grok_*/HANDOFF_LATEST.md`
   - Использовать как транспорт для синхронизации состояния.

## 3. Список файлов, которые будут изменены (предварительный)

### Новые файлы
- `docs/governance/DISTRIBUTED_AGENTS_ANALYSIS.md` — этот документ.
- `app/state/__init__.py` + `app/state/backends/` (pluggable state: db, redis)
- `tests/test_state_backends.py` (базовые тесты)
- `docs/architecture/DISTRIBUTED_AGENTS.md` (документация по failover — не создан)
- `app/health.py` или расширение observability для readiness.

### Изменяемые файлы (что именно)
- `app/task_store.py`:
  - Добавить абстракцию `TaskStateStore` с backends.
  - Опционально: Redis backend для быстрого state + DB для durability.
- `app/config.py`:
  - Новые поля: `state_backend: str = "db"` ("db", "redis", "hybrid"), `redis_state_ttl` и т.д.
- `app/api.py`:
  - Улучшить webhook: идемпотентный setup, graceful delete на shutdown, distributed lock при переключении.
  - Логирование всех webhook событий.
- `app/bot/manager.py`:
  - Вынести in-memory state в `TaskStateStore` где возможно.
  - Добавить graceful shutdown хуки.
- `app/queue.py`:
  - Опционально: поддержка альтернатив (чтобы можно было Celery/RQ).
- `app/entrypoints/worker.py` и `app/tasks.py`:
  - Добавить обработку "stale" задач из state.
- `scripts/dev_run_all.py`:
  - Улучшить graceful shutdown, health probes.
- `tests/test_grok_max_bridge.py`, `tests/test_worker_facts.py` и новые:
  - Тесты для нового state.
- `requirements.txt` (если добавим опциональные зависимости — с комментариями).
- `docker-compose.yml` (опционально postgres/redis tuning).

### Удаление (только если дубликат)
- Нет явных дубликатов. `app/task_store.py` — каноническое место.

**Обратная совместимость:** Все изменения через feature flags / default = текущая реализация (db + sqlite). Миграции DB не ломающие.

## 4. Выявленные слабые места (по промпту + реальному коду)

- **C1 (единое состояние):** TaskStore использует только DB. In-memory в боте теряется. Нет атомарности между enqueue и state. При failover worker — "queued" задачи могут потеряться из вида.
- **C2 (гонка webhook):** Простой setWebhook без проверки текущего состояния. При переключении polling↔webhook или multi-instance — Telegram вернёт ошибку. Нет lock'а.
- **C5 (NAT):** Локалка недоступна — решено через bridges (Grok MAX/TG как "удалённый терминал") + webhook в проде. Но нет автоматического failover между локал/сервер агентом.
- Другие: Git slow для handoff, нет мониторинга (хотя observability есть), worker не graceful (SimpleWorker), отсутствие distributed locks.

## 5. Подходы к реализации (общий план) + Выполненные шаги

### C1: Единое состояние (потеря задач при failover) — ВЫПОЛНЕНО (базовая версия)

**Подходы (как требовалось):**

**А) Redis как основное/дополнительное хранилище состояния (рекомендовано и реализовано)**
- Плюсы: быстро, атомарно, TTL, pub/sub готово, уже есть в проекте (docker + config).
- Минусы: дополнительная зависимость (но уже есть).
- Реализация: `app/state/redis_backend.py` + pluggable `get_state_backend()`.

**Б) SQLite + Git синхронизация**
- Плюсы: нет новых сервисов.
- Минусы: медленный, конфликты, не для distributed.
- Отклонено как основное (оставлено как fallback).

**В) In-memory + сообщения**
- Плюсы: минимум зависимостей.
- Минусы: полная потеря при рестарте.
- Используется только для transient UX state в manager.py.

**Почему выбрано А + pluggable:**
- Сохраняет 100% совместимость (default="db").
- Позволяет выбрать в .env: `STATE_BACKEND=db|redis`.
- Добавлены тесты.
- Используется существующая Redis.

**Что сделано:**
- `app/state/__init__.py` — фабрика + протокол.
- `app/state/db_backend.py` — извлечён старый код.
- `app/state/redis_backend.py` — новый backend.
- `app/config.py` — `state_backend`.
- `app/task_store.py` — теперь фасад (все старые функции работают).
- `tests/test_state_backends.py` — 4 теста (прошли).

Все изменения обратимы (убрать STATE_BACKEND → старое поведение).

### C2: Гонка webhook при переключении — ОТЛОЖЕНО

**Подходы:**
1. Distributed lock (Redis) + идемпотентный setWebhook + graceful delete на shutdown.
2. Single active instance enforcement (через dev_run_all style + DB flag).
3. Полностью внешний (nginx + health-check переключение).

Рекомендация: #1 (использовать уже имеющийся Redis).

**Блокер:** нужен прод-сервер с webhook-режимом и возможность multi-instance failover.

### C5: NAT / локалка — ОТЛОЖЕНО

**Подходы:**
1. Улучшить Grok bridges (уже частично делают) + автоматический handoff.
2. Tailscale / Wireguard mesh для агентов.
3. Cloud relay (но это усложняет).

Рекомендация: Улучшить bridges + документировать в DISTRIBUTED_AGENTS.md.

**Частично вне трека:** Tailscale для дашборда (личное использование) — см. `scripts/remote_dashboard_urls.ps1`.

### Следующие шаги (при возобновлении)

1. Появился прод-сервер → C2 (webhook lock).
2. Нужен публичный доступ без VPN → C5 (туннель/nginx).
3. `IMPLEMENTATION_PLAN.md` — создать по AGENT_PRIME TASK_2.
4. Тесты failover + обновление dev_run_all.

---
*Результат TASK_1 из AGENT_PRIME. Обновлено при постановке трека на паузу (2026-06-22).*
