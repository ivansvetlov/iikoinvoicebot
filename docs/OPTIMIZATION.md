# OPTIMIZATION / План оптимизации (декомпозиция)

## Этап 1 — Рефакторинг кода и структуры
- [ ] Разбить `app/bot/manager.py` на модули: `auth.py`, `file_handlers.py`, `state_manager.py`
- [ ] Ввести типизацию (mypy) и линтеры (ruff) для всего проекта
- [ ] Рефакторить асинхронную логику в manager.py для избежания race conditions (pending_tasks, media_groups)
- [ ] Убрать bare except в api.py, заменить на конкретные исключения
- [x] Удалить `app/logs/` (мёртвая папка, все логи → `logs/`)
- [x] `_append_cost_log` в `pipeline.py`: переписан на append-only (убрано полное перечтение CSV)

## Этап 2 — Тестирование и надежность
- [ ] Добавить unit-тесты (pytest) для `app/services/pipeline.py` и `app/parsers/`
- [ ] Создать интеграционные тесты для API (`/process`, `/process-batch`)
- [ ] Добавить моки для внешних зависимостей (iiko, OpenAI) в тестах
- [ ] Провести QA по docs/TESTCASES.md и зафиксировать результаты

## Этап 3 — Масштабируемость и мониторинг
- [ ] Добавить мониторинг ошибок (Sentry) для backend и bot
- [ ] Ввести метрики (Prometheus) для запросов, LLM-стоимости, времени обработки
- [ ] Оптимизировать использование Redis/RQ (connection pooling, retries)
- [ ] Добавить кэширование для часто используемых данных (user settings)

## Этап 4 — Производительность и UX
- [ ] Оптимизировать OCR и LLM вызовы (batch processing, caching)
- [ ] Улучшить детектор мусора (понизить пороги, стоп-слова)
- [ ] Добавить rate limiting на уровне API (не только bot)
- [ ] Ввести A/B тестирование для режимов (fast/accurate)
- [x] BOM: `env_file_encoding="utf-8-sig"` в config; `scripts/strip_bom.py` для массовой очистки

## Этап 5 — Документация и поддержка
- [ ] Дополнить docstrings во всех модулях
- [ ] Создать API-документацию (Swagger/OpenAPI)
- [ ] Написать runbook для деплоя и откатов
- [ ] Добавить health-checks для всех компонентов

## Выявлено из dialogue_dump (Copilot-сессия)
- [x] Убрать `_auto_process_pending` (5с таймер) — корень зависания при одном файле
- [ ] Исключить повторное создание bot.py процессов (lock-файл есть, но PyCharm обходит)
- [ ] Заменить `apply_patch` / `Set-Content` workflow на инструменты без BOM-инъекции
- [ ] Компилировать (`py_compile`) после каждой правки — агент пропускал NameError/ImportError
- [ ] Убрать мёртвый код: остатки Tesseract (PSM/OEM/TESSDATA_PREFIX), Cloudflare Worker, invoice_client.py

