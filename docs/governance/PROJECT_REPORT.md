# Отчёт о проекте (с 2026-06-06)

> **Период:** с `2026-06-06 01:50:49` (старт сессии Grok / «grok era») по `2026-07-03`
> **Ветка:** `feature/channel-max` (HEAD `48286f2`)
> **Источники:** git log, `AGENT_HANDOFF.md`, `MEMORY_BANK.md`, `TODO.md`, незакоммиченные изменения
> **Полный список файлов:** Приложение E (447 путей, `st_ctime ≥ 2026-06-06 01:50:49`)

---

## 1. Резюме

За период проект прошёл путь от **stage6 (iiko + post-recognition UX)** к **параллельному каналу MAX** и **инфраструктуре удалённой разработки** (Grok bridges, dashboard, handoff).

| Трек | Статус на 2026-07-03 |
|------|----------------------|
| **Ядро invoice bot (Telegram)** | Стабильный MVP; в прод-ветке не трогаем |
| **Stage6 / iiko demo stand** | API OK; E2E scaffold есть; полный ручной прогон — в очереди |
| **MAX invoice bot** | Phase 2 MVP в `experiments/max_invoice_bot/`; живые тесты идут |
| **Grok TG + MAX bridges** | Работают; dashboard на `:8765`; handoff/journal |
| **Распознавание (race)** | OpenAI vision ∥ SotaOCR hybrid — **локально**, не в последнем коммите |
| **Distributed agents (AGENT_PRIME)** | **Пауза** — нет VPS |
| **Telegram «Избранное» research** | **Пауза** — нет API credentials |

**Главный блокер сейчас:** SotaOCR `upstream_unavailable` (worker `109.230.162.227:8090` → connection refused) + периодические таймауты OpenAI vision через VPN. Preflight перед upload убран (экономия ~20 с).

---

## 2. Хронология

### 2026-06-06 — 2026-06-14 (до первых коммитов периода)

Работа велась в контексте stage6: status-card, retry, stale-task reaper, iiko first-fill. Коммиты этого блока **старше** cutoff 06.06, но легли в основу спринта.

Ключевые темы из handoff §40–§49 (апрель–июнь): `/status` UX, iiko API-first (без Playwright), demo stand `840-786-070.iiko.it`.

### 2026-06-15 — Post-audit + post-recognition UX

**Коммиты:** `32b0569`, `f00f4e9`

- Governance: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `COMPREHENSIVE_AUDIT.md` → `docs/governance/`
- `PROJECT_CLONE_PROMPT.md`, `AUDIT_REMEDIATION_PLAN.md`, planning-артефакты
- Post-recognition UX: `invoice_keyboards.py`, `invoice_posting.py`, callback-flow в `manager.py`
- LLM unit resolver + owner rules (`app/services/invoice_flow/`)
- Тесты: `test_invoice_flow_conversion.py`, `test_user_store.py`, `test_worker_facts.py`

### 2026-06-17 — Фокус stage6, пауза favorites

**Handoff §52–§53** (часть в коммитах kickoff-ветки)

- Реструктуризация `docs/` → подпапки `governance/`, `operations/`, `architecture/`, `iiko/`, `planning/`, `assets/`
- Demo stand восстановлен (`IIKO_AUTH_OK`)
- Telegram Saved Messages research отложен (блокер `TELEGRAM_API_ID/HASH`)

### 2026-06-18–19 — dev_run_all hardening

**Коммиты:** `67c511d`, `a82aacd`

- Lock `tmp/dev_run_all.lock` + stale cleanup + `--force`
- Pre-kill всех процессов проекта (uvicorn, worker, bot)
- Исправлен hang/suicide при pre-kill на Windows

### 2026-06-20 — Grok Telegram bridge + unified dashboard

**Коммиты:** `434f100` … `3ae3852` (6 коммитов за день)

| Deliverable | Файлы |
|-------------|-------|
| Grok TG bridge | `experiments/grok_telegram_bridge/`, `METAPROMPT.md` |
| Unified dashboard | `docs/assets/project-dashboard.html`, `scripts/render_todo_dashboard.py`, `dashboard_data.py` |
| Chat dump hub | `scripts/export_grok_chat_dump.py`, `grok chat dump` (канон) |
| TG export prep | `scripts/export_telegram_saved.py` |
| Bridge journal | `work_journal.py`, `HANDOFF_LATEST.md` в `data/private/grok_bridge/` |

Dashboard = roadmap (`TODO.md`) + зеркало `logs/` + metrics + reports + online probe + bridge runs.

### 2026-06-22 — Grok MAX bridge + старт MAX invoice bot

**Коммит:** `7db9ce5`

- `experiments/grok_max_bridge/` — отдельный dev-бот (`GROK_MAX_BRIDGE_TOKEN`)
- Общие модули с TG bridge (formatter, runner, journal)
- Начало порта invoice bot → MAX (`INVOICE_BOT_MAX_PORT_PLAN.md`)

### 2026-06-29 — MAX invoice bot в git + stage6 pipeline

**Коммит:** `48286f2` (+5378 / −256 строк)

| Компонент | Что сделано |
|-----------|-------------|
| MAX invoice bot | `experiments/max_invoice_bot/` — bot, task_watcher, keyboards, messaging |
| Token guard | `app/bot/max_tokens.py` — `MAX_INVOICE_BOT_TOKEN` ≠ bridge token |
| Channel protocol | `app/channels/protocol.py` |
| State backends | `app/state/` — db + redis (C1 AGENT_PRIME) |
| Pipeline | `INVOICE_FLOW_MODE=modular`, НДС-колонка, фильтр «В том числе НДС» |
| Bridge ctl | `scripts/grok_bridge_ctl.py` — надёжный restart (~10 с) |
| Dashboard serve | `scripts/serve_project_dashboard.py` |
| AGENT_PRIME | `docs/governance/AGENT_PRIME.md`, `DISTRIBUTED_AGENTS_ANALYSIS.md` |
| Skills | diagnosing-bugs, file-search, find-skills, grill-me |

### 2026-06-30 — 2026-07-03 — Локальная работа (не закоммичено)

По `git status` и `MEMORY_BANK`:

| Изменение | Файлы / суть |
|-----------|--------------|
| Recognition race | `app/services/recognition_race.py`, `app/ocr/`, `tests/test_max_recognition_race.py` |
| SotaOCR client | `app/ocr/`, `scripts/probe_sotaocr.py`, `prompts/sotaocr_hybrid_parse.txt` |
| Preflight убран | `experiments/max_invoice_bot/bot.py` — сразу upload, без ~20 с проверки |
| dev_stack_ctl | `scripts/dev_stack_ctl.py` — быстрый restart PyCharm 1/2/5 (~15 с) |
| Memory Bank | `docs/governance/MEMORY_BANK.md` — continuity между тредами |
| MAX bot fixes | дубли ответов, кнопки после «обработать сейчас», processing_status |
| VPN / WireGuard | `config/wireguard/`, `scripts/ensure_sotaocr_vpn.ps1` |
| Tray monitor | worktree `dev-process-monitor` (IDE RAM + bank size) |

**Диагностика заявки `20260703_164149`:** `llm_timeout` = SotaOCR upstream down + OpenAI vision timeout 45 с.

---

## 3. Коммиты за период (git)

```
48286f2  2026-06-29  feat(channel-max): MAX invoice bot, token guard, stage6 pipeline
7db9ce5  2026-06-22  feat(max): Grok MAX bridge on feature/channel-max
3ae3852  2026-06-20  feat(bridge): chat dump hub + export scripts
b4642d2  2026-06-20  feat(bridge): dashboard integration + telegram export config
aaaa73f  2026-06-20  feat(bridge): unified project dashboard
bef4587  2026-06-20  feat(exp): bridge buttons, journal handoff, HTML todo dashboard
3f9bf4a  2026-06-20  feat(exp): METAPROMPT and auto --rules
434f100  2026-06-20  feat(exp): Grok Telegram bridge
a82aacd  2026-06-19  fix: dev_run_all pre-kill must not hang or suicide
67c511d  2026-06-19  chore: harden dev_run_all orchestrator
f00f4e9  2026-06-15  feat(stage6): post-recognition UX, unit flow, docs sync
32b0569  2026-06-15  stage6: LLM unit resolver, governance docs, planning
```

**Итого:** 12 коммитов, ~7k+ строк добавлено в последнем крупном коммите.

---

## 4. Архитектура (текущая)

```
Пользователь
    ├── Telegram bot (app/entrypoints/bot.py)     ← production MVP, не трогаем
    ├── MAX invoice bot (experiments/max_invoice_bot/)  ← новый канал
    └── Grok bridges (experiments/grok_*_bridge/) ← удалённая разработка

Backend (uvicorn :8000)
    └── /process → Redis/RQ queue → Worker
            └── pipeline.py → recognition_race (локально) → iiko

Handoff / continuity
    ├── docs/governance/AGENT_HANDOFF.md   (изменения кода)
    ├── docs/governance/MEMORY_BANK.md     (решения, диагностика)
    └── grok chat dump                      (история, ненадёжно — kotlin.Unit)
```

**Запуск dev-стека (PyCharm):**

```powershell
.\.venv\Scripts\python.exe scripts\dev_stack_ctl.py restart   # 1 backend + 2 worker + 5 MAX bot
.\.venv\Scripts\python.exe scripts\dev_stack_ctl.py status
```

---

## 5. Новые файлы по зонам (с 06.06, без шума)

Сгруппировано по `st_ctime ≥ 2026-06-06 01:50:49`, исключены `.venv`, `terminals`, `agent-tools`, `.worktrees`:

| Зона | ~файлов | Назначение |
|------|---------|------------|
| `data/private/` | 53 | Bridge runs, journal, handoff, sessions |
| `data/jobs/` | 26 | Payload заявок на распознавание |
| `experiments/grok_telegram_bridge/` | 23 | TG bridge |
| `experiments/max_invoice_bot/` | 12 | MAX invoice bot |
| `app/services/` | 10 | pipeline, recognition_race, invoice_flow |
| `.agents/skills/` | 9 | Agent skills (dev-stack-restart, powershell-windows, …) |
| `docs/governance/` | 8 | AGENT_PRIME, MEMORY_BANK, ANALYSIS, … |
| `experiments/grok_max_bridge/` | 8 | MAX bridge |
| `app/ocr/` | 4 | SotaOCR client (локально) |

Полный сырой список — **Приложение E** (447 путей).

---

## 6. Открытые задачи

### Активно (MAX + recognition)

- [ ] Закоммитить race + SotaOCR + dev_stack_ctl + MEMORY_BANK
- [ ] Стабилизировать SotaOCR upstream или fallback только на OpenAI
- [ ] Живой прогон MAX: файл → распознавание → кнопки → без дублей
- [ ] `BOT_COMMAND_MATRIX` — сверка паритета с Telegram

### Stage6 / iiko

- [ ] Ручной прогон `docs/iiko/INVOICE_FLOW_TESTING.md` на demo stand
- [ ] Сервисное меню: rollback/clear-stock (сейчас заглушки)
- [ ] Политика posting: `NEW` draft vs `PROCESSED` auto-post

### Post-audit

- [ ] CI: tests + lint на push/PR
- [ ] Branch protection на main
- [ ] `requirements-dev.txt` + pre-commit

### Пауза

- Distributed agents (C2/C5 ждут VPS)
- Telegram favorites research (ждёт API credentials)

---

## 7. Быстрые проверки

```powershell
# Unit-тесты MAX + tokens
.\.venv\Scripts\python.exe -m unittest tests.test_max_invoice_bot tests.test_max_tokens -v

# Recognition race (локально)
.\.venv\Scripts\python.exe -m unittest tests.test_max_recognition_race -v

# SotaOCR probe
.\.venv\Scripts\python.exe scripts\probe_sotaocr.py

# Диагностика заявки
.\.venv\Scripts\python.exe scripts\diagnose_request.py <request_id>

# Dashboard
.\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
# → docs/assets/project-dashboard.html
```

---

## 8. Примечание об исправлении

Предыдущая попытка (2026-07-03) сломалась:

1. PowerShell-команда с `$cutoff` / `$_.CreationTime` — переменные съедены оболочкой агента → ParserError на каждом файле.
2. Скрипт `scripts/_scan_grok_era_files.py` не был создан (`tmp/grok_era_files.txt` содержит только ошибку).

Этот отчёт собран через **git + handoff + Python-агрегацию по директориям**, без рекурсивного скана всего диска.

---

*Сгенерировано: 2026-07-03. Обновлять вручную после значимых сессий или дописывать в `MEMORY_BANK.md`.*

---

# Приложения (для верификации другим агентом)

> **Цель:** другой агент может **независимо** проверить: что создано, какие задачи решались, чем доказано.
> **Регенерация списка файлов:** `.venv\Scripts\python.exe scripts\_gen_report_appendix.py`

## Приложение A — Чеклист верификации

Порядок для агента-верификатора:

| # | Проверка | Команда / файл | Ожидание |
|---|----------|----------------|----------|
| 1 | Ветка и HEAD | `git branch -v` | `* feature/channel-max` @ `48286f2` |
| 2 | 12 коммитов с 06.06 | `git log --since=2026-06-06 --oneline` | см. Приложение C |
| 3 | Незакоммиченный diff | `git status --short` + `git diff --stat` | см. Приложение D |
| 4 | MAX bot тесты | `.venv\Scripts\python.exe -m unittest tests.test_max_invoice_bot tests.test_max_tokens -v` | OK |
| 5 | Recognition race | `.venv\Scripts\python.exe -m unittest tests.test_max_recognition_race -v` | OK (локально) |
| 6 | SotaOCR probe | `.venv\Scripts\python.exe scripts\probe_sotaocr.py` | balance может OK, upload может FAIL (`upstream_unavailable`) |
| 7 | Диагностика заявки | `.venv\Scripts\python.exe scripts\diagnose_request.py 20260703_164149_100_____183900520` | `llm_timeout`, две причины |
| 8 | Handoff актуален | `docs/governance/AGENT_HANDOFF.md` §59–§61 | MAX, race, dev_stack_ctl |
| 9 | Memory Bank | `docs/governance/MEMORY_BANK.md` | preflight убран, SotaOCR upstream |
| 10 | Файлы с 06.06 | Приложение E (447 путей) | сверить выборочно ключевые |

**Красные флаги (не считать «готово»):**
- `tmp/grok_era_files.txt` — битый артефакт (ошибка несуществующего скрипта)
- `scripts/_patch_*.py` — одноразовые патчи агента, не прод-код
- `.worktrees/dev-process-monitor/` — отдельный worktree, не основная ветка
- Chat dumps (`grok chat dump`, `dump chat max theme`) — часто `kotlin.Unit`, ненадёжны как единственный источник

---

## Приложение B — Журнал задач: что просили → как решили

Формат: **запрос/симптом → диагностика → решение → артефакты**.

### B.1 Stage6 post-recognition UX (2026-06-15)

| | |
|---|---|
| **Запрос** | После распознавания — кнопки редактировать/оприходовать/синхронизировать как в Codex-сессиях |
| **Диагностика** | UX был в `dump stage6` / `last chat`, не в git |
| **Решение** | Восстановлены `invoice_keyboards.py`, `invoice_posting.py`, callbacks в `manager.py`, worker replies |
| **Артефакты** | коммиты `f00f4e9`, `32b0569`; тесты `test_invoice_flow_conversion.py` |
| **Проверка** | `python -m unittest tests.test_worker_facts tests.test_invoice_flow_conversion -v` |

### B.2 dev_run_all зависает / suicide (2026-06-19)

| | |
|---|---|
| **Симптом** | Pre-kill вешает оркестратор; убивает сам себя |
| **Диагностика** | `taskkill /T` без timeout; слишком широкий match процессов |
| **Решение** | PID self-protection, `taskkill /T /F` с timeout, узкий match bot |
| **Артефакты** | `a82aacd`, `67c511d`; `scripts/dev_run_all.py` |
| **Проверка** | `python scripts/dev_run_all.py --help`; lock `tmp/dev_run_all.lock` |

### B.3 Удалённая разработка: Grok bridges (2026-06-20)

| | |
|---|---|
| **Запрос** | Работа дома (Cursor) + в дороге (TG/MAX); видеть результат агента |
| **Решение** | `experiments/grok_telegram_bridge/` + `grok_max_bridge/`; journal + HANDOFF; `grok -p --rules METAPROMPT` |
| **Артефакты** | коммиты `434f100`…`3ae3852`; `data/private/grok_*_bridge/journal.jsonl` |
| **Проверка** | `python -m unittest tests.test_grok_bridge tests.test_grok_max_bridge -v` |

### B.4 Unified dashboard (2026-06-20)

| | |
|---|---|
| **Запрос** | Один HTML: TODO + logs + metrics + reports; кнопки в TG |
| **Решение** | `project-dashboard.html`, `dashboard_data.py`, `render_todo_dashboard.py`, `serve_project_dashboard.py :8765` |
| **Артефакты** | `aaaa73f`; Tailscale URL в `.env` для MAX кнопки «Дашборд» |
| **Проверка** | `python scripts/render_todo_dashboard.py` → открыть HTML |

### B.5 Grok bridge restart ломается (2026-06-22)

| | |
|---|---|
| **Симптом** | Restart 20+ мин, дубли процессов, PowerShell Start-Process timeout 30s |
| **Диагностика** | Параллельные restart, тяжёлый WMI scan, дашборд дубли |
| **Решение** | Переписан `grok_bridge_ctl.py`: Popen, lock, stop→wait→start (~10s) |
| **Артефакты** | `scripts/grok_bridge_ctl.py`; run config `0__all.xml --with-grok-max` |
| **Проверка** | `python scripts/grok_bridge_ctl.py status --bridge max` |

### B.6 MAX invoice bot port (2026-06-22–29)

| | |
|---|---|
| **Запрос** | Invoice bot в MAX; TG не трогать; паритет поведения |
| **Решение** | `experiments/max_invoice_bot/`: enqueue без chat_id → `task_watcher` poll `task_store`; user `max:{uid}` |
| **Токены** | `MAX_INVOICE_BOT_TOKEN` (Pusher) ≠ `GROK_MAX_BRIDGE_TOKEN`; guard `max_tokens.py` |
| **Артефакты** | `7db9ce5`, `48286f2`; PyCharm `5__max_invoice_bot.xml` |
| **Проверка** | `python -m unittest tests.test_max_invoice_bot tests.test_max_tokens -v` |

### B.7 Дубли ответов в MAX (2026-06-30)

| | |
|---|---|
| **Симптом** | Два ответа на каждое сообщение |
| **Диагностика** | Два процесса MAX bot и/или worker editMessage fallback при `ok=false` |
| **Решение** | Worker проверяет Telegram `ok` перед fallback; изоляция MAX от TG bot |
| **Артефакты** | `app/tasks.py` (в коммите); `experiments/max_invoice_bot/bot.py` (локально) |
| **Проверка** | один PID на `5__max_invoice_bot`; лог `logs/max_bot.log` |

### B.8 Кнопка остаётся после «обработать сейчас» (2026-07-02)

| | |
|---|---|
| **Симптом** | Текст меняется на «обрабатываю», inline-кнопка активна |
| **Запрос** | Как в TG — убрать кнопку; сначала проверить API MAX |
| **Решение** | Edit message + `reply_markup` empty / удаление клавиатуры через MAX API |
| **Артефакты** | `experiments/max_invoice_bot/keyboards.py`, `bot.py`, `processing_status.py` |
| **Проверка** | ручной прогон: нажать «обработать сейчас» → кнопки нет |

### B.9 Долгая обработка / 7 минут (2026-07-02–03)

| | |
|---|---|
| **Симптом** | Обработка ~7 мин vs ожидаемые ~30 с |
| **Диагностика** | Preflight SotaOCR + последовательный fallback; нет параллельного race |
| **Решение** | `recognition_race.py` — OpenAI vision ∥ SotaOCR hybrid; winner по качеству/времени |
| **Артефакты** | `app/services/recognition_race.py`, `app/ocr/sotaocr_client.py`, `tests/test_max_recognition_race.py` |
| **Проверка** | `python -m unittest tests.test_max_recognition_race -v` |

### B.10 llm_timeout заявка 20260703_164149 (2026-07-03)

| | |
|---|---|
| **Симптом** | MAX upload → ~47 с → `llm_timeout` |
| **Диагностика** | `scripts/probe_sotaocr.py`: balance OK, upload → `upstream_unavailable` (109.230.162.227:8090); OpenAI vision timeout 45s |
| **Решение пользователя** | Убрать preflight (~20 с ложной задержки); ошибки из worker |
| **Артефакты** | `MEMORY_BANK.md`; `tmp/diagnose_20260703_164149_*.json`; preflight удалён из `max_invoice_bot/bot.py` |
| **Проверка** | `python scripts/diagnose_request.py 20260703_164149_100_____183900520` |

### B.11 Agent shell ломает restart (2026-07-03)

| | |
|---|---|
| **Симптом** | `(cd ; uvicorn --port 8000)` → PowerShell ParserError, ретраи 1–2 мин |
| **Решение** | `scripts/dev_stack_ctl.py` — читает PyCharm run configs 1/2/5, subprocess без PS-обёрток |
| **Артефакты** | `dev_stack_ctl.py`, `.agents/skills/dev-stack-restart/SKILL.md`, `logs/dev_stack/*.log` |
| **Проверка** | `python scripts/dev_stack_ctl.py restart` (~15–20 с) |

### B.12 Отчёт о проекте с 06.06 (2026-07-03)

| | |
|---|---|
| **Запрос** | Исправленный файл отчёта; приложение для верификации |
| **Провал v1** | PS `$cutoff` съеден; `_scan_grok_era_files.py` не создан |
| **Решение v2** | `scripts/_gen_report_appendix.py` + этот документ + Приложение E |
| **Артефакты** | `docs/governance/PROJECT_REPORT.md`, `tmp/project_report_appendix_files.txt` |

---

## Приложение C — Git: полные сообщения коммитов

```
48286f2 2026-06-29 feat(channel-max): MAX invoice bot, token guard, stage6 pipeline
  Add experiments/max_invoice_bot with task_store polling.
  Separate MAX_INVOICE_BOT_TOKEN from GROK_MAX_BRIDGE_TOKEN.
  Wire modular invoice flow, VAT hints, worker editMessage fix.

7db9ce5 2026-06-22 feat(max): Grok MAX bridge on feature/channel-max
  maxapi adapter; callback ack fix; BridgeMsg parity; allowlist open when empty.

3ae3852 2026-06-20 feat(bridge): chat dump hub + export scripts

b4642d2 2026-06-20 feat(bridge): dashboard integration + telegram export + job timeout

aaaa73f 2026-06-20 feat(bridge): unified project dashboard

bef4587 2026-06-20 feat(exp): bridge buttons, journal handoff, HTML todo dashboard

3f9bf4a 2026-06-20 feat(exp): METAPROMPT and auto --rules

434f100 2026-06-20 feat(exp): Grok Telegram bridge

a82aacd 2026-06-19 fix: dev_run_all pre-kill must not hang or suicide

67c511d 2026-06-19 chore: harden dev_run_all orchestrator

f00f4e9 2026-06-15 feat(stage6): post-recognition UX, unit flow, docs sync

32b0569 2026-06-15 stage6: LLM unit resolver, governance docs, planning
```

---

## Приложение D — Незакоммиченные изменения (на 2026-07-03)

### D.1 `git status --short`

```
 M .env.example
 M .gitignore
 M app/bot/manager.py
 M app/bot/messages.py
 M app/config.py
 M app/services/pipeline.py          (+240 строк — race integration)
 M app/utils/user_messages.py
 M docs/AGENTS.md
 M docs/README.md
 M docs/governance/AGENT_HANDOFF.md
 M docs/operations/DEV_SETUP.md
 M experiments/max_invoice_bot/*.py  (bot, task_watcher, attachments, …)
 M requirements.txt
 M scripts/README.md
 M tests/test_invoice_recognition.py
 M tests/test_max_invoice_bot.py
 M tests/test_user_messages.py
?? app/ocr/                          (SotaOCR client, vpn, html_table)
?? app/services/recognition_race.py
?? app/services/recognition_preflight.py  (создан, потом preflight убран из bot)
?? docs/governance/MEMORY_BANK.md
?? docs/governance/PROJECT_REPORT.md
?? scripts/dev_stack_ctl.py
?? scripts/probe_sotaocr.py
?? tests/test_max_recognition_race.py
?? tests/test_sotaocr_client.py
?? .agents/skills/dev-stack-restart/
?? .agents/skills/powershell-windows/
?? config/wireguard/
?? prompts/sotaocr_hybrid_parse.txt
```

### D.2 `git diff --stat` (tracked only)

```
22 files changed, 943 insertions(+), 82 deletions(-)
```

Ключевые локальные файлы **вне diff** (untracked): `recognition_race.py`, `app/ocr/`, `dev_stack_ctl.py`, тесты race/sotaocr.

---

## Приложение E — Полный список файлов (st_ctime ≥ 2026-06-06 01:50:49)

Исключены: `.venv`, `__pycache__`, `.git`, `node_modules`, `terminals`, `agent-tools`.
**Всего: 447** (включая runtime: `data/jobs/`, `logs/`, `tmp/`, worktree-копию).

Формат: `created | modified | size_bytes | path`

```
2026-06-12 23:23 | 2026-06-22 17:41 |       1593 | CONTRIBUTING.md
2026-06-12 23:23 | 2026-06-22 17:41 |       1084 | LICENSE
2026-06-12 23:23 | 2026-06-22 17:41 |       1561 | SECURITY.md
2026-06-12 23:23 | 2026-06-22 17:41 |       8160 | app/services/invoice_flow/llm_unit_resolver.py
2026-06-12 23:23 | 2026-06-22 17:41 |       2826 | app/services/invoice_flow/owner_rules.py
2026-06-12 23:23 | 2026-06-15 00:04 |      19893 | last chat
2026-06-12 23:23 | 2026-06-22 17:41 |       9621 | tests/e2e_helpers.py
2026-06-12 23:23 | 2026-06-29 23:00 |      12019 | tests/test_e2e_invoice_posting.py
2026-06-12 23:23 | 2026-06-22 17:41 |       7103 | tests/test_invoice_flow_conversion.py
2026-06-12 23:23 | 2026-06-22 17:41 |       2563 | tests/test_user_store.py
2026-06-12 23:23 | 2026-06-22 17:41 |       1714 | tests/test_worker_facts.py
2026-06-15 00:04 | 2026-06-22 17:41 |       6951 | app/iiko/import_export.py
2026-06-15 00:04 | 2026-06-22 17:41 |      44352 | app/iiko/server_client.py
2026-06-15 00:04 | 2026-06-22 17:41 |      13647 | app/services/category_onboarding.py
2026-06-15 00:04 | 2026-06-22 17:41 |        647 | app/services/invoice_flow/__init__.py
2026-06-15 00:04 | 2026-06-22 17:41 |       1293 | app/services/invoice_flow/models.py
2026-06-15 00:04 | 2026-06-22 17:41 |      10078 | app/services/invoice_flow/resolver.py
2026-06-15 00:04 | 2026-06-29 23:00 |       2665 | app/services/invoice_flow/runner.py
2026-06-15 00:04 | 2026-06-22 17:41 |       7991 | app/services/invoice_flow/unit_conversion.py
2026-06-15 00:04 | 2026-06-22 17:41 |       1085 | scripts/iiko_auth_check.py
2026-06-15 00:04 | 2026-06-22 17:41 |      16552 | scripts/iiko_complex_loader.py
2026-06-15 00:04 | 2026-06-22 17:41 |       9957 | scripts/iiko_reset_stock.py
2026-06-15 00:04 | 2026-06-22 17:41 |       2597 | scripts/invoice_flow_compare.py
2026-06-15 00:04 | 2026-06-22 17:41 |       3551 | tests/test_category_onboarding.py
2026-06-15 00:04 | 2026-06-22 17:41 |       2571 | tests/test_iiko_import_export.py
2026-06-15 00:04 | 2026-06-22 17:41 |      15231 | tests/test_iiko_server_client.py
2026-06-15 00:04 | 2026-06-22 17:41 |       3655 | tests/test_invoice_flow_runner.py
2026-06-15 00:05 | 2026-06-17 17:45 |       1625 | logs/requests/20260406_120000_000_42.json
2026-06-15 00:05 | 2026-06-30 22:45 |      24808 | logs/requests/users/42.jsonl
2026-06-15 00:05 | 2026-06-17 17:45 |        772 | logs/requests/20260408_121000_000_42.json
2026-06-15 00:05 | 2026-06-17 17:45 |        772 | logs/requests/20260408_120000_000_42.json
2026-06-15 00:13 | 2026-06-22 17:41 |       3557 | app/bot/invoice_keyboards.py
2026-06-15 00:13 | 2026-06-22 17:41 |       3447 | app/bot/invoice_posting.py
2026-06-17 17:14 | 2026-06-22 17:41 |       8571 | scripts/export_telegram_saved.py
2026-06-17 17:40 | 2026-06-17 17:40 |        951 | tmp/iiko_quick_check.py
2026-06-17 19:40 | 2026-06-17 19:40 |      85780 | data/jobs/20260617_194015_286_6106711925/20260617_185908_819538_7e0aeaac_invoice_photo.jpg
2026-06-17 19:40 | 2026-06-17 19:40 |        394 | data/jobs/20260617_194015_286_6106711925/payload.json
2026-06-17 22:50 | 2026-06-17 22:50 |      35799 | tmp/diagnose_20260617_194015_286_6106711925.json
2026-06-17 23:27 | 2026-06-17 23:27 |     689170 | data/jobs/20260617_232729_939_6106711925/20260617_225902_572323_3ddb6745_invoice_photo.jpg
2026-06-17 23:27 | 2026-06-17 23:27 |        394 | data/jobs/20260617_232729_939_6106711925/payload.json
2026-06-17 23:30 | 2026-06-17 23:30 |      31290 | tmp/diagnose_20260617_232729_939_6106711925.json
2026-06-17 23:42 | 2026-06-17 23:42 |     689170 | data/jobs/20260617_234259_060_6106711925/20260617_225902_572323_3ddb6745_invoice_photo.jpg
2026-06-17 23:42 | 2026-06-17 23:42 |        394 | data/jobs/20260617_234259_060_6106711925/payload.json
2026-06-17 23:44 | 2026-06-17 23:44 |      16852 | tmp/llm_debug/20260617_234408_269_bad_function_json_20260617_225902_572323_3ddb6745_invoice_photo_prep.jpg.json
2026-06-17 23:44 | 2026-06-18 00:13 |      34110 | tmp/diagnose_20260617_234259_060_6106711925.json
2026-06-18 00:12 | 2026-06-18 00:12 |       1272 | tmp/find_code.py
2026-06-19 00:09 | 2026-06-19 00:09 |        959 | tmp/debug_prekill.py
2026-06-19 00:13 | 2026-06-19 00:13 |       2070 | tmp/e2e_process_invoice.py
2026-06-19 00:13 | 2026-06-19 00:13 |     177674 | data/jobs/20260619_001331_285_6106711925/invoice test.pdf
2026-06-19 00:13 | 2026-06-19 00:13 |        323 | data/jobs/20260619_001331_285_6106711925/payload.json
2026-06-19 00:17 | 2026-06-19 00:17 |      29412 | tmp/diagnose_20260619_001331_285_6106711925.json
2026-06-19 10:26 | 2026-06-19 10:26 |     689170 | data/jobs/20260619_102606_289_6106711925/20260619_102434_379221_2fd485df_20260617_225902_572323_3ddb6745_invoice_photo.jpg
2026-06-19 10:26 | 2026-06-19 10:26 |        458 | data/jobs/20260619_102606_289_6106711925/payload.json
2026-06-19 10:27 | 2026-06-19 10:27 |     689170 | data/jobs/20260619_102736_331_6106711925/20260619_102434_379221_2fd485df_20260617_225902_572323_3ddb6745_invoice_photo.jpg
2026-06-19 10:27 | 2026-06-19 10:27 |        458 | data/jobs/20260619_102736_331_6106711925/payload.json
2026-06-19 10:41 | 2026-06-19 10:41 |       1116 | tmp/disable_extra_vpns.ps1
2026-06-19 10:52 | 2026-06-19 10:52 |     689170 | data/jobs/20260619_105250_267_6106711925/20260619_102434_379221_2fd485df_20260617_225902_572323_3ddb6745_invoice_photo.jpg
2026-06-19 10:52 | 2026-06-19 10:52 |        458 | data/jobs/20260619_105250_267_6106711925/payload.json
2026-06-19 10:55 | 2026-06-19 10:55 |      32213 | tmp/diagnose_20260619_105250_267_6106711925.json
2026-06-19 10:56 | 2026-06-19 11:31 |      11552 | tmp/monitor_openai_availability.py
2026-06-19 10:56 | 2026-06-19 11:06 |        896 | tmp/availability_20260619_105632.csv
2026-06-19 11:06 | 2026-06-19 11:06 |       9005 | tmp/availability_20260619_105632.json
2026-06-19 11:06 | 2026-06-19 11:06 |       6590 | tmp/availability_20260619_105632.svg
2026-06-19 11:41 | 2026-06-19 11:41 |       1717 | tmp/availability_20260619_113140.csv
2026-06-19 11:41 | 2026-06-19 11:41 |      18099 | tmp/availability_20260619_113140.json
2026-06-19 11:41 | 2026-06-19 11:41 |      11577 | tmp/availability_20260619_113140.html
2026-06-20 01:47 | 2026-06-22 17:41 |         56 | experiments/__init__.py
2026-06-20 01:47 | 2026-06-22 17:41 |         57 | experiments/grok_telegram_bridge/__init__.py
2026-06-20 01:47 | 2026-06-22 20:01 |       2734 | experiments/grok_telegram_bridge/config.py
2026-06-20 01:47 | 2026-06-22 17:41 |       2062 | experiments/grok_telegram_bridge/session_store.py
2026-06-20 01:47 | 2026-06-22 17:57 |       3727 | experiments/grok_telegram_bridge/formatter.py
2026-06-20 01:47 | 2026-06-22 17:41 |        205 | experiments/grok_telegram_bridge/security.py
2026-06-20 01:47 | 2026-06-22 17:41 |       7586 | experiments/grok_telegram_bridge/grok_runner.py
2026-06-20 01:47 | 2026-06-22 17:41 |        855 | experiments/grok_telegram_bridge/tester.py
2026-06-20 01:48 | 2026-06-22 22:44 |      15565 | experiments/grok_telegram_bridge/bot.py
2026-06-20 01:48 | 2026-06-22 17:41 |        214 | experiments/grok_telegram_bridge/__main__.py
2026-06-20 01:49 | 2026-06-22 22:42 |       7660 | tests/test_grok_bridge.py
2026-06-20 01:49 | 2026-06-22 17:41 |       2732 | experiments/grok_telegram_bridge/README.md
2026-06-20 01:49 | 2026-06-22 17:41 |        201 | scripts/run_grok_bridge.ps1
2026-06-20 02:14 | 2026-06-22 17:41 |       4265 | experiments/grok_telegram_bridge/ARCHITECTURE.md
2026-06-20 02:22 | 2026-06-20 12:53 |        431 | tmp/commit_msg.txt
2026-06-20 04:59 | 2026-06-20 04:59 |        239 | data/private/grok_bridge/sessions.json
2026-06-20 05:06 | 2026-06-22 17:41 |        281 | experiments/grok_telegram_bridge/rules_loader.py
2026-06-20 05:07 | 2026-06-20 05:07 |       1824 | tmp/patch_handoff.py
2026-06-20 05:07 | 2026-06-20 05:07 |        120 | tmp/commit_msg2.txt
2026-06-20 10:50 | 2026-06-22 22:42 |       1189 | experiments/grok_telegram_bridge/keyboards.py
2026-06-20 10:50 | 2026-06-22 18:20 |       2958 | experiments/grok_telegram_bridge/context_store.py
2026-06-20 10:50 | 2026-06-22 17:41 |       1200 | experiments/grok_telegram_bridge/git_snapshot.py
2026-06-20 10:50 | 2026-06-22 20:26 |      10139 | experiments/grok_telegram_bridge/work_journal.py
2026-06-20 10:50 | 2026-06-22 17:41 |       1038 | experiments/grok_telegram_bridge/onboarding.py
2026-06-20 10:51 | 2026-06-20 10:51 |        261 | tmp/commit_msg3.txt
2026-06-20 10:58 | 2026-06-22 17:41 |      11786 | scripts/dashboard_data.py
2026-06-20 10:58 | 2026-06-22 20:01 |       5333 | experiments/grok_telegram_bridge/dashboard_hub.py
2026-06-20 11:00 | 2026-06-20 11:00 |        515 | tmp/_patch_dash.py
2026-06-20 11:01 | 2026-06-20 11:01 |       3133 | tmp/_patch_bot.py
2026-06-20 11:01 | 2026-06-20 11:01 |       1054 | tmp/_patch_tests.py
2026-06-20 11:01 | 2026-06-20 11:01 |       1088 | tmp/_patch_readme.py
2026-06-20 11:20 | 2026-06-20 11:20 |        511 | .idea/agentbridgeCodeGraph.xml
2026-06-20 11:49 | 2026-06-20 11:49 |        641 | tmp/_inspect_db.py
2026-06-20 11:49 | 2026-06-22 21:16 |     246725 | grok chat dump
2026-06-20 11:54 | 2026-06-22 17:41 |       8621 | scripts/export_grok_chat_dump.py
2026-06-20 11:54 | 2026-06-20 11:54 |        933 | tmp/_scan_sessions.py
2026-06-20 12:03 | 2026-06-22 17:41 |       1071 | experiments/grok_telegram_bridge/chat_dump_hub.py
2026-06-20 12:04 | 2026-06-20 12:04 |       4761 | tmp/_patch_handoff.py
2026-06-20 13:48 | 2026-06-20 13:48 |       1507 | tmp/check_tg_network.ps1
2026-06-20 14:58 | 2026-06-22 17:41 |         62 | experiments/grok_max_bridge/__init__.py
2026-06-20 14:58 | 2026-06-29 22:59 |       2754 | experiments/grok_max_bridge/config.py
2026-06-20 14:58 | 2026-06-22 20:26 |        927 | experiments/grok_max_bridge/keyboards.py
2026-06-20 14:58 | 2026-06-22 17:41 |        204 | experiments/grok_max_bridge/__main__.py
2026-06-20 14:58 | 2026-06-22 20:26 |      18202 | experiments/grok_max_bridge/bot.py
2026-06-20 14:59 | 2026-06-22 17:41 |       3907 | experiments/grok_max_bridge/README.md
2026-06-20 14:59 | 2026-06-22 21:15 |       5650 | tests/test_grok_max_bridge.py
2026-06-20 15:00 | 2026-06-20 15:00 |        219 | tmp/_check_max_bridge.py
2026-06-21 02:29 | 2026-06-22 17:41 |       5172 | experiments/grok_max_bridge/ARCHITECTURE.md
2026-06-21 22:09 | 2026-06-22 22:51 |        274 | data/private/grok_max_bridge/sessions.json
2026-06-21 22:09 | 2026-06-22 21:16 |      44872 | data/private/grok_max_bridge/context/183900520.jsonl
2026-06-21 22:10 | 2026-06-21 22:10 |       2623 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/meta.json
2026-06-21 22:10 | 2026-06-21 22:10 |        592 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/prompt.txt
2026-06-21 22:10 | 2026-06-21 22:10 |       1063 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/response.txt
2026-06-21 22:10 | 2026-06-21 22:10 |       1158 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/git_after.json
2026-06-21 22:10 | 2026-06-21 22:10 |       1158 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/git_before.json
2026-06-21 22:10 | 2026-06-21 22:10 |     422588 | data/private/grok_max_bridge/runs/20260621T190918-10cbdf43/git_diff.patch
2026-06-21 22:10 | 2026-06-22 21:16 |      19667 | data/private/grok_max_bridge/journal.jsonl
2026-06-21 22:10 | 2026-06-22 21:16 |       3436 | data/private/grok_max_bridge/HANDOFF_LATEST.md
2026-06-21 22:12 | 2026-06-21 22:12 |       2534 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/meta.json
2026-06-21 22:12 | 2026-06-21 22:12 |        123 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/prompt.txt
2026-06-21 22:12 | 2026-06-21 22:12 |       1687 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/response.txt
2026-06-21 22:12 | 2026-06-21 22:12 |       1160 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/git_after.json
2026-06-21 22:12 | 2026-06-21 22:12 |       1160 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/git_before.json
2026-06-21 22:12 | 2026-06-21 22:12 |     422990 | data/private/grok_max_bridge/runs/20260621T191131-677099f4/git_diff.patch
2026-06-21 22:17 | 2026-06-21 22:17 |       2559 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/meta.json
2026-06-21 22:17 | 2026-06-21 22:17 |        264 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/prompt.txt
2026-06-21 22:17 | 2026-06-21 22:17 |       2214 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/response.txt
2026-06-21 22:17 | 2026-06-21 22:17 |       1160 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/git_before.json
2026-06-21 22:17 | 2026-06-21 22:17 |       1292 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/git_after.json
2026-06-21 22:17 | 2026-06-21 22:17 |     426516 | data/private/grok_max_bridge/runs/20260621T191331-9864e208/git_diff.patch
2026-06-21 22:18 | 2026-06-21 22:18 |       1276 | data/private/grok_max_bridge/runs/20260621T191833-16253698/meta.json
2026-06-21 22:18 | 2026-06-21 22:18 |         89 | data/private/grok_max_bridge/runs/20260621T191833-16253698/prompt.txt
2026-06-21 22:18 | 2026-06-21 22:18 |       1292 | data/private/grok_max_bridge/runs/20260621T191833-16253698/git_before.json
2026-06-21 22:18 | 2026-06-21 22:18 |         52 | data/private/grok_max_bridge/runs/20260621T191833-16253698/response.txt
2026-06-21 22:18 | 2026-06-21 22:18 |       1292 | data/private/grok_max_bridge/runs/20260621T191833-16253698/git_after.json
2026-06-21 22:18 | 2026-06-21 22:18 |     426516 | data/private/grok_max_bridge/runs/20260621T191833-16253698/git_diff.patch
2026-06-21 22:22 | 2026-06-21 22:22 |       1933 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/meta.json
2026-06-21 22:22 | 2026-06-21 22:22 |        683 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/prompt.txt
2026-06-21 22:22 | 2026-06-21 22:22 |       1292 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/git_before.json
2026-06-21 22:22 | 2026-06-21 22:22 |        115 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/response.txt
2026-06-21 22:22 | 2026-06-21 22:22 |       1292 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/git_after.json
2026-06-21 22:22 | 2026-06-21 22:22 |     426516 | data/private/grok_max_bridge/runs/20260621T192135-d9bfe0cd/git_diff.patch
2026-06-22 17:32 | 2026-06-22 21:50 |        308 | ANALYSIS.md
2026-06-22 17:33 | 2026-06-22 21:50 |       2136 | app/state/__init__.py
2026-06-22 17:33 | 2026-06-22 17:41 |       4184 | app/state/db_backend.py
2026-06-22 17:33 | 2026-06-22 17:41 |       6645 | app/state/redis_backend.py
2026-06-22 17:33 | 2026-06-22 17:41 |       2419 | tests/test_state_backends.py
2026-06-22 17:34 | 2026-06-22 17:34 |       3140 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/meta.json
2026-06-22 17:34 | 2026-06-22 17:34 |       6321 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/prompt.txt
2026-06-22 17:34 | 2026-06-22 17:34 |       4865 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/response.txt
2026-06-22 17:34 | 2026-06-22 17:34 |       1276 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/git_before.json
2026-06-22 17:34 | 2026-06-22 17:34 |       1494 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/git_after.json
2026-06-22 17:34 | 2026-06-22 17:34 |     434186 | data/private/grok_max_bridge/runs/20260622T143141-e2651d51/git_diff.patch
2026-06-22 17:41 | 2026-06-22 20:26 |       6928 | experiments/grok_telegram_bridge/messages.py
2026-06-22 17:41 | 2026-06-22 17:41 |        260 | .github/CODEOWNERS
2026-06-22 17:41 | 2026-06-22 17:41 |        597 | .github/pull_request_template.md
2026-06-22 17:41 | 2026-07-03 18:15 |       3953 | docs/AGENTS.md
2026-06-22 17:41 | 2026-07-03 18:15 |       8156 | docs/README.md
2026-06-22 17:41 | 2026-06-22 17:41 |       6639 | docs/architecture/ARCHITECTURE.md
2026-06-22 17:41 | 2026-06-22 17:41 |       3461 | docs/architecture/OPTIMIZATION.md
2026-06-22 17:41 | 2026-06-22 17:41 |       8674 | docs/assets/.todo-dashboard.svg
2026-06-22 17:41 | 2026-06-29 23:00 |     145221 | docs/assets/project-dashboard.html
2026-06-22 17:41 | 2026-06-29 23:00 |     145221 | docs/assets/todo-dashboard.html
2026-06-22 17:41 | 2026-07-03 18:51 |      50059 | docs/governance/AGENT_HANDOFF.md
2026-06-22 17:41 | 2026-06-22 17:41 |       5590 | docs/governance/AUDIT_REMEDIATION_PLAN.md
2026-06-22 17:41 | 2026-06-22 17:41 |      16329 | docs/governance/COMPREHENSIVE_AUDIT.md
2026-06-22 17:41 | 2026-06-22 21:50 |       3011 | docs/governance/DEFERRED_BRANCH_NOTES.md
2026-06-22 17:41 | 2026-06-22 17:41 |       7072 | docs/governance/PROJECT_CLONE_PROMPT.md
2026-06-22 17:41 | 2026-06-22 17:41 |       6398 | docs/iiko/IIKO_API_GAPS.md
2026-06-22 17:41 | 2026-06-22 17:41 |       2260 | docs/iiko/IIKO_DEMO_STAND.md
2026-06-22 17:41 | 2026-06-22 17:41 |       1473 | docs/iiko/INVOICE_FLOW_EXPERIMENT.md
2026-06-22 17:41 | 2026-06-22 17:41 |       3925 | docs/iiko/INVOICE_FLOW_TESTING.md
2026-06-22 17:41 | 2026-06-22 17:41 |       9688 | docs/operations/BOT_COMMAND_MATRIX.md
2026-06-22 17:41 | 2026-06-22 17:41 |       1778 | docs/operations/BOT_EVENT_CODES.md
2026-06-22 17:41 | 2026-06-22 17:41 |       7189 | docs/operations/DEBUG.md
2026-06-22 17:41 | 2026-07-03 18:49 |       9938 | docs/operations/DEV_SETUP.md
2026-06-22 17:41 | 2026-06-22 17:41 |      12498 | docs/operations/SKILL.md
2026-06-22 17:41 | 2026-06-22 17:41 |       9925 | docs/operations/TESTCASES.md
2026-06-22 17:41 | 2026-06-22 17:41 |       4849 | docs/planning/BRANCH_WAIT_OPTIMIZATION_PLAN.md
2026-06-22 17:41 | 2026-06-22 17:41 |       8337 | docs/planning/CATEGORY_ONBOARDING_QUESTION_IMPACT.md
2026-06-22 17:41 | 2026-06-22 17:41 |       9231 | docs/planning/MENU_DOMAIN_EXPANSION_PLAN.md
2026-06-22 17:41 | 2026-06-29 23:00 |      19666 | docs/planning/TODO.md
2026-06-22 17:41 | 2026-06-22 17:41 |       4502 | experiments/grok_telegram_bridge/agents/METAPROMPT.md
2026-06-22 17:41 | 2026-06-22 17:41 |       2321 | experiments/grok_telegram_bridge/agents/REMOTE_HANDOFF.md
2026-06-22 17:41 | 2026-06-22 17:41 |        896 | experiments/grok_telegram_bridge/agents/tester.md
2026-06-22 17:41 | 2026-06-22 17:41 |         36 | fixtures/smoke/duplicate_blob.bin
2026-06-22 17:41 | 2026-06-22 17:41 |        166 | fixtures/smoke/invoice_control.txt
2026-06-22 17:41 | 2026-06-22 17:41 |        103 | fixtures/smoke/receipt_control.txt
2026-06-22 17:41 | 2026-06-22 17:41 |       1009 | prompts/invoice_parser_units_fork.txt
2026-06-22 17:41 | 2026-06-22 17:41 |       1049 | prompts/invoice_unit_resolution_fork.txt
2026-06-22 17:41 | 2026-06-22 17:41 |     253952 | .agentbridge/conversation.db
2026-06-22 17:41 | 2026-06-22 18:29 |       5355 | experiments/grok_max_bridge/agents/METAPROMPT.md
2026-06-22 17:42 | 2026-06-22 17:42 |        205 | scripts/run_grok_max_bridge.ps1
2026-06-22 17:49 | 2026-06-22 21:51 |      19034 | docs/governance/AGENT_PRIME.md
2026-06-22 17:51 | 2026-06-22 17:51 |       3314 | tmp/patch_slash.py
2026-06-22 17:58 | 2026-06-22 17:58 |       2654 | tmp/patch_max_bold.py
2026-06-22 17:58 | 2026-06-22 23:07 |      12574 | scripts/grok_bridge_ctl.py
2026-06-22 17:58 | 2026-06-22 17:58 |        190 | scripts/restart_grok_max_bridge.ps1
2026-06-22 17:59 | 2026-06-22 17:59 |       1259 | tmp/patch_ctl.py
2026-06-22 18:00 | 2026-06-22 18:00 |        543 | tmp/scan_bridge.py
2026-06-22 18:21 | 2026-06-22 18:21 |       3401 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/meta.json
2026-06-22 18:21 | 2026-06-22 18:21 |       1854 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/prompt.txt
2026-06-22 18:21 | 2026-06-22 18:21 |       5594 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/response.txt
2026-06-22 18:21 | 2026-06-22 18:21 |       1336 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/git_before.json
2026-06-22 18:21 | 2026-06-22 18:21 |       1595 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/git_after.json
2026-06-22 18:21 | 2026-06-22 18:21 |     445360 | data/private/grok_max_bridge/runs/20260622T151849-d05ead96/git_diff.patch
2026-06-22 18:30 | 2026-06-22 23:04 |       3805 | scripts/serve_project_dashboard.py
2026-06-22 18:59 | 2026-06-22 19:00 |       1877 | scripts/remote_dashboard_urls.ps1
2026-06-22 18:59 | 2026-06-22 18:59 |        720 | config/cloudflared/config.example.yml
2026-06-22 20:53 | 2026-06-22 20:53 |       5446 | .agents/skills/find-skills/SKILL.md
2026-06-22 20:53 | 2026-07-03 17:02 |       1532 | skills-lock.json
2026-06-22 21:01 | 2026-06-22 21:01 |       1351 | .idea/runConfigurations/0__all.xml
2026-06-22 21:09 | 2026-06-22 21:06 |       8595 | .agents/skills/file-search/SKILL.md
2026-06-22 21:11 | 2026-06-22 21:11 |        154 | .agents/skills/grill-me/SKILL.md
2026-06-22 21:11 | 2026-06-22 21:11 |       8670 | .agents/skills/diagnosing-bugs/SKILL.md
2026-06-22 21:11 | 2026-06-22 21:11 |       1205 | .agents/skills/diagnosing-bugs/scripts/hitl-loop.template.sh
2026-06-22 21:16 | 2026-06-22 21:16 |       2521 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/meta.json
2026-06-22 21:16 | 2026-06-22 21:16 |         71 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/prompt.txt
2026-06-22 21:16 | 2026-06-22 21:16 |       4064 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/response.txt
2026-06-22 21:16 | 2026-06-22 21:16 |       2509 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/git_before.json
2026-06-22 21:16 | 2026-06-22 21:16 |       2604 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/git_after.json
2026-06-22 21:16 | 2026-06-22 21:16 |     488997 | data/private/grok_max_bridge/runs/20260622T181236-f6509718/git_diff.patch
2026-06-22 21:50 | 2026-06-22 21:50 |      15694 | docs/governance/DISTRIBUTED_AGENTS_ANALYSIS.md
2026-06-22 22:03 | 2026-06-22 22:33 |       9461 | docs/planning/INVOICE_BOT_MAX_PORT_PLAN.md
2026-06-22 22:03 | 2026-06-22 22:03 |       2751 | app/channels/protocol.py
2026-06-22 22:03 | 2026-06-22 22:03 |        468 | app/channels/__init__.py
2026-06-22 22:03 | 2026-06-22 22:03 |         92 | app/max_bot/__init__.py
2026-06-22 22:03 | 2026-06-22 22:33 |        164 | app/max_bot/README.md
2026-06-22 22:03 | 2026-06-22 22:33 |        655 | app/entrypoints/max_bot.py
2026-06-22 22:03 | 2026-06-22 22:03 |       1246 | tests/test_channel_protocol.py
2026-06-22 22:23 | 2026-06-29 22:59 |       1269 | experiments/max_invoice_bot/config.py
2026-06-22 22:23 | 2026-06-30 14:33 |        591 | experiments/max_invoice_bot/user_ids.py
2026-06-22 22:23 | 2026-06-30 14:30 |        912 | experiments/max_invoice_bot/keyboards.py
2026-06-22 22:23 | 2026-07-02 23:10 |       2711 | experiments/max_invoice_bot/attachments.py
2026-06-22 22:23 | 2026-06-30 14:45 |       3362 | experiments/max_invoice_bot/messaging.py
2026-06-22 22:23 | 2026-07-02 23:58 |       5745 | experiments/max_invoice_bot/task_watcher.py
2026-06-22 22:24 | 2026-06-22 22:24 |        669 | experiments/max_invoice_bot/edit_state.py
2026-06-22 22:31 | 2026-07-03 18:15 |      69534 | experiments/max_invoice_bot/bot.py
2026-06-22 22:31 | 2026-06-22 22:31 |        116 | experiments/max_invoice_bot/__main__.py
2026-06-22 22:33 | 2026-07-02 23:12 |       4308 | tests/test_max_invoice_bot.py
2026-06-22 22:33 | 2026-06-22 22:33 |        247 | scripts/run_max_invoice_bot.ps1
2026-06-22 22:33 | 2026-06-22 22:33 |       1216 | experiments/max_invoice_bot/README.md
2026-06-22 22:33 | 2026-06-22 22:33 |       1681 | experiments/max_invoice_bot/ARCHITECTURE.md
2026-06-22 22:39 | 2026-06-22 22:39 |       1332 | .idea/runConfigurations/5__max_invoice_bot.xml
2026-06-22 22:46 | 2026-06-22 22:46 |       1368 | .idea/runConfigurations/6__grok_bridge_tg.xml
2026-06-22 22:47 | 2026-06-22 22:47 |       1336 | .idea/runConfigurations/4__grok_bridge__MAX_.xml
2026-06-22 22:53 | 2026-06-22 22:53 |          6 | tmp/grok_telegram_bridge.lock
2026-06-22 22:55 | 2026-06-22 22:59 |       1389 | .idea/runConfigurations/7__dashboard.xml
2026-06-29 22:59 | 2026-06-29 22:59 |       2248 | app/bot/max_tokens.py
2026-06-29 23:00 | 2026-06-29 23:00 |        638 | tests/test_max_tokens.py
2026-06-29 23:09 | 2026-06-29 23:09 |       3614 | scripts/probe_max_bots.py
2026-06-29 23:22 | 2026-06-29 23:23 |        804 | scripts/test_iiko_auth_pairs.py
2026-06-29 23:59 | 2026-06-29 23:59 |        230 | app/ocr/__init__.py
2026-06-29 23:59 | 2026-06-30 04:49 |      18402 | app/ocr/sotaocr_client.py
2026-06-29 23:59 | 2026-06-30 00:17 |       5113 | tests/test_sotaocr_client.py
2026-06-30 00:03 | 2026-07-03 18:05 |        415 | logs/sotaocr_probe/error.json
2026-06-30 00:06 | 2026-03-03 17:36 |     101492 | logs/sotaocr_probe/invoice.jpg
2026-06-30 00:08 | 2026-06-30 00:08 |        691 | logs/sotaocr_probe/tiny.jpg
2026-06-30 00:10 | 2026-07-03 18:05 |        397 | logs/sotaocr_probe/balance.json
2026-06-30 00:16 | 2026-06-30 04:49 |       3761 | scripts/probe_sotaocr.py
2026-06-30 04:44 | 2026-06-30 04:50 |        359 | logs/sotaocr_probe/job.json
2026-06-30 04:44 | 2026-06-30 04:50 |       3533 | logs/sotaocr_probe/result.txt
2026-06-30 04:48 | 2026-06-30 12:57 |       3609 | scripts/ensure_sotaocr_vpn.ps1
2026-06-30 04:48 | 2026-07-02 23:58 |       3168 | app/ocr/vpn.py
2026-06-30 04:53 | 2026-06-30 12:56 |        380 | config/wireguard/vpn188958_split_sotaocr.conf
2026-06-30 04:54 | 2026-06-30 12:56 |        450 | config/wireguard/vpn188958_split_sotaocr.conf.example
2026-06-30 04:54 | 2026-06-30 04:54 |        689 | app/ocr/html_table.py
2026-06-30 04:54 | 2026-06-30 13:34 |       9933 | scripts/compare_sotaocr_pipeline.py
2026-06-30 13:04 | 2026-06-30 13:22 |         23 | logs/sotaocr_compare/pipeline.json
2026-06-30 13:04 | 2026-06-30 13:04 |       3534 | logs/sotaocr_compare/sotaocr_raw.txt
2026-06-30 13:04 | 2026-06-30 13:22 |       2068 | logs/sotaocr_compare/sotaocr_plain.txt
2026-06-30 13:04 | 2026-06-30 13:22 |        715 | logs/sotaocr_compare/sotaocr.json
2026-06-30 13:04 | 2026-06-30 13:22 |        432 | logs/sotaocr_compare/comparison.json
2026-06-30 13:22 | 2026-06-30 13:22 |       1273 | logs/sotaocr_compare/hybrid.json
2026-06-30 13:34 | 2026-06-30 13:34 |        975 | prompts/sotaocr_hybrid_parse.txt
2026-06-30 13:34 | 2026-06-30 13:34 |        797 | logs/requests/20260630_133438_057_42.json
2026-06-30 14:16 | 2026-06-30 14:16 |        281 | logs/archive/dashboard_serve.err.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |        216 | logs/archive/dashboard_serve.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |        698 | logs/archive/grok_max_bridge.err.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |         40 | logs/archive/grok_max_bridge.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |       4896 | logs/archive/grok_telegram_bridge.err.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |         45 | logs/archive/grok_telegram_bridge.log.gz
2026-06-30 14:16 | 2026-06-30 14:16 |      10007 | logs/archive/mailbox/42.jsonl.gz
2026-06-30 14:16 | 2026-06-30 14:16 |       1916 | logs/archive/mailbox/77.jsonl.gz
2026-06-30 14:16 | 2026-06-30 14:18 |       6265 | logs/max_bot.log
2026-06-30 14:40 | 2026-06-30 14:40 |      88162 | data/jobs/20260630_144016_272_____183900520/20260630_144009_864717_d2cf2ff9_invoice_photo.jpg
2026-06-30 14:40 | 2026-06-30 14:40 |        401 | data/jobs/20260630_144016_272_____183900520/payload.json
2026-06-30 14:47 | 2026-06-30 14:47 |       2722 | logs/requests/20260630_144016_272_____183900520.json
2026-06-30 14:47 | 2026-06-30 14:47 |       2103 | logs/requests/users/____183900520.jsonl
2026-06-30 15:05 | 2026-06-30 15:05 |        797 | logs/requests/20260630_150536_359_42.json
2026-06-30 15:05 | 2026-06-30 15:05 |        797 | logs/requests/20260630_150545_013_42.json
2026-06-30 15:22 | 2026-06-30 15:22 |      75636 | dump chat max theme
2026-06-30 22:43 | 2026-07-02 23:59 |       5246 | app/services/recognition_preflight.py
2026-06-30 22:43 | 2026-07-02 23:58 |       8890 | app/services/recognition_race.py
2026-06-30 22:43 | 2026-06-30 22:43 |        464 | experiments/max_invoice_bot/processing_status.py
2026-06-30 22:44 | 2026-07-03 18:16 |       3954 | tests/test_max_recognition_race.py
2026-06-30 22:45 | 2026-06-30 22:45 |        797 | logs/requests/20260630_224517_396_42.json
2026-06-30 22:53 | 2026-06-30 22:53 |       5274 | scripts/_patch_preflight.py
2026-06-30 22:56 | 2026-06-30 22:56 |        860 | scripts/_fix_sota_sync.py
2026-06-30 23:08 | 2026-06-30 23:08 |      86820 | data/jobs/20260630_230858_574_____183900520/20260630_230852_877515_3ff6134b_invoice_photo.jpg
2026-06-30 23:08 | 2026-06-30 23:08 |        401 | data/jobs/20260630_230858_574_____183900520/payload.json
2026-07-02 23:21 | 2026-07-02 23:21 |      86820 | data/jobs/20260702_232156_480_____183900520/20260702_232132_085549_3305ed1c_invoice_photo.jpg
2026-07-02 23:21 | 2026-07-02 23:21 |        401 | data/jobs/20260702_232156_480_____183900520/payload.json
2026-07-02 23:31 | 2026-07-02 23:31 |        897 | .idea/runConfigurations/8__vpn.xml
2026-07-03 00:03 | 2026-07-03 00:03 |      86820 | data/jobs/20260703_000342_427_____183900520/20260703_000314_168926_1a5666ff_invoice_photo.jpg
2026-07-03 00:03 | 2026-07-03 00:03 |        401 | data/jobs/20260703_000342_427_____183900520/payload.json
2026-07-03 16:41 | 2026-07-03 16:41 |      86820 | data/jobs/20260703_164149_100_____183900520/20260703_164121_776805_60f1b663_invoice_photo.jpg
2026-07-03 16:41 | 2026-07-03 16:41 |        401 | data/jobs/20260703_164149_100_____183900520/payload.json
2026-07-03 16:44 | 2026-07-03 16:44 |      20176 | tmp/diagnose_20260703_164149_100_____183900520.json
2026-07-03 16:45 | 2026-07-03 16:45 |        155 | .worktrees/dev-process-monitor/.editorconfig
2026-07-03 16:45 | 2026-07-03 16:45 |       1222 | .worktrees/dev-process-monitor/.env.example
2026-07-03 16:45 | 2026-07-03 16:45 |        226 | .worktrees/dev-process-monitor/.gitattributes
2026-07-03 16:45 | 2026-07-03 16:46 |        926 | .worktrees/dev-process-monitor/.gitignore
2026-07-03 16:45 | 2026-07-03 16:45 |         67 | .worktrees/dev-process-monitor/.idea/.gitignore
2026-07-03 16:45 | 2026-07-03 16:45 |       1326 | .worktrees/dev-process-monitor/.idea/runConfigurations/0__all.xml
2026-07-03 16:45 | 2026-07-03 16:45 |       1350 | .worktrees/dev-process-monitor/.idea/runConfigurations/1__backend.xml
2026-07-03 16:45 | 2026-07-03 16:45 |       1309 | .worktrees/dev-process-monitor/.idea/runConfigurations/2__worker.xml
2026-07-03 16:45 | 2026-07-03 16:45 |       1303 | .worktrees/dev-process-monitor/.idea/runConfigurations/3__bot.xml
2026-07-03 16:45 | 2026-07-03 16:45 |        205 | .worktrees/dev-process-monitor/Dockerfile
2026-07-03 16:45 | 2026-07-03 16:45 |        462 | .worktrees/dev-process-monitor/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |       1589 | .worktrees/dev-process-monitor/app/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |         50 | .worktrees/dev-process-monitor/app/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |      10964 | .worktrees/dev-process-monitor/app/api.py
2026-07-03 16:45 | 2026-07-03 16:45 |        761 | .worktrees/dev-process-monitor/app/bot/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |         48 | .worktrees/dev-process-monitor/app/bot/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |       5131 | .worktrees/dev-process-monitor/app/bot/backend_client.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1269 | .worktrees/dev-process-monitor/app/bot/event_codes.py
2026-07-03 16:45 | 2026-07-03 16:45 |       6323 | .worktrees/dev-process-monitor/app/bot/file_storage.py
2026-07-03 16:45 | 2026-07-03 16:45 |      65139 | .worktrees/dev-process-monitor/app/bot/manager.py
2026-07-03 16:45 | 2026-07-03 16:45 |      14370 | .worktrees/dev-process-monitor/app/bot/messages.py
2026-07-03 16:45 | 2026-07-03 16:45 |       4141 | .worktrees/dev-process-monitor/app/config.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1748 | .worktrees/dev-process-monitor/app/db.py
2026-07-03 16:45 | 2026-07-03 16:45 |         84 | .worktrees/dev-process-monitor/app/entrypoints/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |        838 | .worktrees/dev-process-monitor/app/entrypoints/bot.py
2026-07-03 16:45 | 2026-07-03 16:45 |       7417 | .worktrees/dev-process-monitor/app/entrypoints/invoice_llm_client.py
2026-07-03 16:45 | 2026-07-03 16:45 |        126 | .worktrees/dev-process-monitor/app/entrypoints/main.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1002 | .worktrees/dev-process-monitor/app/entrypoints/worker.py
2026-07-03 16:45 | 2026-07-03 16:45 |        839 | .worktrees/dev-process-monitor/app/errors.py
2026-07-03 16:45 | 2026-07-03 16:45 |        611 | .worktrees/dev-process-monitor/app/iiko/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |         61 | .worktrees/dev-process-monitor/app/iiko/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |       5525 | .worktrees/dev-process-monitor/app/iiko/playwright_client.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1372 | .worktrees/dev-process-monitor/app/models.py
2026-07-03 16:45 | 2026-07-03 16:45 |       7629 | .worktrees/dev-process-monitor/app/observability.py
2026-07-03 16:45 | 2026-07-03 16:45 |        877 | .worktrees/dev-process-monitor/app/parsers/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |         88 | .worktrees/dev-process-monitor/app/parsers/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |       6287 | .worktrees/dev-process-monitor/app/parsers/file_text_extractor.py
2026-07-03 16:45 | 2026-07-03 16:45 |      21436 | .worktrees/dev-process-monitor/app/parsers/invoice_parser.py
2026-07-03 16:45 | 2026-07-03 16:45 |        427 | .worktrees/dev-process-monitor/app/queue.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1936 | .worktrees/dev-process-monitor/app/schemas.py
2026-07-03 16:45 | 2026-07-03 16:45 |        831 | .worktrees/dev-process-monitor/app/services/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |         59 | .worktrees/dev-process-monitor/app/services/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |       5468 | .worktrees/dev-process-monitor/app/services/invoice_validator.py
2026-07-03 16:45 | 2026-07-03 16:45 |      91945 | .worktrees/dev-process-monitor/app/services/pipeline.py
2026-07-03 16:45 | 2026-07-03 16:45 |       2396 | .worktrees/dev-process-monitor/app/services/user_store.py
2026-07-03 16:45 | 2026-07-03 16:45 |       2288 | .worktrees/dev-process-monitor/app/task_store.py
2026-07-03 16:45 | 2026-07-03 16:45 |       8149 | .worktrees/dev-process-monitor/app/tasks.py
2026-07-03 16:45 | 2026-07-03 16:45 |        587 | .worktrees/dev-process-monitor/app/utils/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |        204 | .worktrees/dev-process-monitor/app/utils/__init__.py
2026-07-03 16:45 | 2026-07-03 16:45 |       6800 | .worktrees/dev-process-monitor/app/utils/user_messages.py
2026-07-03 16:45 | 2026-07-03 16:45 |        881 | .worktrees/dev-process-monitor/docker-compose.yml
2026-07-03 16:45 | 2026-07-03 16:45 |       8674 | .worktrees/dev-process-monitor/docs/.todo-dashboard.svg
2026-07-03 16:45 | 2026-07-03 16:45 |       1612 | .worktrees/dev-process-monitor/docs/AGENTS.md
2026-07-03 16:45 | 2026-07-03 16:45 |      29540 | .worktrees/dev-process-monitor/docs/AGENT_HANDOFF.md
2026-07-03 16:45 | 2026-07-03 16:45 |       6377 | .worktrees/dev-process-monitor/docs/ARCHITECTURE.md
2026-07-03 16:45 | 2026-07-03 16:45 |       9688 | .worktrees/dev-process-monitor/docs/BOT_COMMAND_MATRIX.md
2026-07-03 16:45 | 2026-07-03 16:45 |       1778 | .worktrees/dev-process-monitor/docs/BOT_EVENT_CODES.md
2026-07-03 16:45 | 2026-07-03 16:45 |       5973 | .worktrees/dev-process-monitor/docs/DEBUG.md
2026-07-03 16:45 | 2026-07-03 16:45 |       8089 | .worktrees/dev-process-monitor/docs/DEV_SETUP.md
2026-07-03 16:45 | 2026-07-03 16:45 |       3459 | .worktrees/dev-process-monitor/docs/OPTIMIZATION.md
2026-07-03 16:45 | 2026-07-03 16:45 |       5278 | .worktrees/dev-process-monitor/docs/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |      12498 | .worktrees/dev-process-monitor/docs/SKILL.md
2026-07-03 16:45 | 2026-07-03 16:45 |       9917 | .worktrees/dev-process-monitor/docs/TESTCASES.md
2026-07-03 16:45 | 2026-07-03 16:45 |      11655 | .worktrees/dev-process-monitor/docs/TODO.md
2026-07-03 16:45 | 2026-07-03 16:45 |         36 | .worktrees/dev-process-monitor/fixtures/smoke/duplicate_blob.bin
2026-07-03 16:45 | 2026-07-03 16:45 |        166 | .worktrees/dev-process-monitor/fixtures/smoke/invoice_control.txt
2026-07-03 16:45 | 2026-07-03 16:45 |        103 | .worktrees/dev-process-monitor/fixtures/smoke/receipt_control.txt
2026-07-03 16:45 | 2026-07-03 16:45 |        337 | .worktrees/dev-process-monitor/nginx_bot.conf
2026-07-03 16:45 | 2026-07-03 16:46 |        298 | .worktrees/dev-process-monitor/requirements.txt
2026-07-03 16:45 | 2026-07-03 18:16 |       1930 | .worktrees/dev-process-monitor/scripts/README.md
2026-07-03 16:45 | 2026-07-03 16:45 |        751 | .worktrees/dev-process-monitor/scripts/archive_logs.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1137 | .worktrees/dev-process-monitor/scripts/check_bom.py
2026-07-03 16:45 | 2026-07-03 16:45 |       4837 | .worktrees/dev-process-monitor/scripts/cleanup_dev_artifacts.py
2026-07-03 16:45 | 2026-07-03 16:45 |      10994 | .worktrees/dev-process-monitor/scripts/dev_run_all.py
2026-07-03 16:45 | 2026-07-03 16:45 |       3297 | .worktrees/dev-process-monitor/scripts/dev_status.py
2026-07-03 16:45 | 2026-07-03 16:45 |       7282 | .worktrees/dev-process-monitor/scripts/diagnose_image.py
2026-07-03 16:45 | 2026-07-03 16:45 |      12712 | .worktrees/dev-process-monitor/scripts/diagnose_request.py
2026-07-03 16:45 | 2026-07-03 16:45 |       2392 | .worktrees/dev-process-monitor/scripts/dump_task_results.py
2026-07-03 16:45 | 2026-07-03 16:45 |        584 | .worktrees/dev-process-monitor/scripts/git.ps1
2026-07-03 16:45 | 2026-07-03 16:45 |       2762 | .worktrees/dev-process-monitor/scripts/llm_costs_rebuild.py
2026-07-03 16:45 | 2026-07-03 16:45 |       4358 | .worktrees/dev-process-monitor/scripts/metrics_report.py
2026-07-03 16:45 | 2026-07-03 16:45 |      10755 | .worktrees/dev-process-monitor/scripts/render_todo_dashboard.py
2026-07-03 16:45 | 2026-07-03 16:45 |       1511 | .worktrees/dev-process-monitor/scripts/set_mode.ps1
2026-07-03 16:45 | 2026-07-03 16:45 |       5111 | .worktrees/dev-process-monitor/scripts/sort_root_files.py
2026-07-03 16:45 | 2026-07-03 16:45 |       3300 | .worktrees/dev-process-monitor/scripts/strip_bom.py
2026-07-03 16:45 | 2026-07-03 16:45 |      18293 | .worktrees/dev-process-monitor/tests/test_bot_stage5.py
2026-07-03 16:45 | 2026-07-03 16:45 |      10521 | .worktrees/dev-process-monitor/tests/test_invoice_recognition.py
2026-07-03 16:45 | 2026-07-03 16:45 |       4833 | .worktrees/dev-process-monitor/tests/test_observability.py
2026-07-03 16:45 | 2026-07-03 16:45 |       2162 | .worktrees/dev-process-monitor/tests/test_user_messages.py
2026-07-03 16:46 | 2026-07-03 19:53 |       6990 | .worktrees/dev-process-monitor/scripts/dev_process_probe.py
2026-07-03 16:46 | 2026-07-03 16:46 |       2610 | .worktrees/dev-process-monitor/scripts/dev_tray_icons.py
2026-07-03 16:46 | 2026-07-03 19:56 |       6410 | .worktrees/dev-process-monitor/scripts/dev_process_monitor.py
2026-07-03 16:46 | 2026-07-03 16:46 |       2077 | .worktrees/dev-process-monitor/tests/test_dev_process_probe.py
2026-07-03 16:46 | 2026-07-03 16:46 |        347 | .worktrees/dev-process-monitor/tests/test_dev_tray_icons.py
2026-07-03 16:46 | 2026-07-03 16:46 |       1390 | .worktrees/dev-process-monitor/.idea/runConfigurations/9__process_monitor.xml
2026-07-03 16:47 | 2026-07-03 19:57 |        760 | .worktrees/dev-process-monitor/scripts/assets/dev_tray/tray_ok.png
2026-07-03 16:47 | 2026-07-03 19:57 |        808 | .worktrees/dev-process-monitor/scripts/assets/dev_tray/tray_partial.png
2026-07-03 16:47 | 2026-07-03 19:57 |        760 | .worktrees/dev-process-monitor/scripts/assets/dev_tray/tray_down.png
2026-07-03 16:47 | 2026-07-03 19:57 |        760 | .worktrees/dev-process-monitor/scripts/assets/dev_tray/tray_idle.png
2026-07-03 16:52 | 2026-07-03 16:52 |       1428 | tmp/tray_monitor_err.log
2026-07-03 16:54 | 2026-07-03 19:56 |       1819 | .worktrees/dev-process-monitor/scripts/run_dev_process_monitor.ps1
2026-07-03 17:02 | 2026-07-03 19:55 |       6478 | .agents/skills/powershell-windows/SKILL.md
2026-07-03 17:02 | 2026-07-03 17:02 |       5137 | .agents/skills/create-pr/SKILL.md
2026-07-03 17:02 | 2026-07-03 17:02 |       4324 | .agents/skills/conventional-commit/SKILL.md
2026-07-03 18:15 | 2026-07-03 18:53 |       5773 | docs/governance/MEMORY_BANK.md
2026-07-03 18:16 | 2026-07-03 19:54 |       4129 | .worktrees/dev-process-monitor/scripts/dev_ide_probe.py
2026-07-03 18:16 | 2026-07-03 18:19 |       2068 | .worktrees/dev-process-monitor/tests/test_dev_process_monitor.py
2026-07-03 18:34 | 2026-07-03 18:34 |      86820 | data/jobs/20260703_183450_345_____183900520/20260703_183445_794888_5a8a0de7_invoice_photo.jpg
2026-07-03 18:34 | 2026-07-03 18:34 |        401 | data/jobs/20260703_183450_345_____183900520/payload.json
2026-07-03 18:48 | 2026-07-03 19:38 |      11780 | scripts/dev_stack_ctl.py
2026-07-03 18:48 | 2026-07-03 18:48 |        601 | scripts/dev_stack_ctl.ps1
2026-07-03 18:48 | 2026-07-03 19:48 |       4119 | .agents/skills/dev-stack-restart/SKILL.md
2026-07-03 18:49 | 2026-07-03 20:13 |      17202 | logs/dev_stack/1.log
2026-07-03 18:49 | 2026-07-03 20:13 |       5066 | logs/dev_stack/2.log
2026-07-03 18:49 | 2026-07-03 19:38 |        416 | logs/dev_stack/5.log
2026-07-03 18:52 | 2026-07-03 19:37 |        304 | logs/dev_stack/start_1.cmd
2026-07-03 18:52 | 2026-07-03 19:38 |        278 | logs/dev_stack/start_2.cmd
2026-07-03 18:52 | 2026-07-03 19:38 |        283 | logs/dev_stack/start_5.cmd
2026-07-03 19:30 | 2026-07-03 19:30 |        777 | scripts/_patch_vpn_ok.py
2026-07-03 19:31 | 2026-07-03 19:31 |       1031 | scripts/_patch_breakaway.py
2026-07-03 19:32 | 2026-07-03 19:32 |       2903 | scripts/_patch_start_min.py
2026-07-03 19:35 | 2026-07-03 19:35 |        357 | scripts/_test_pythonw_start.ps1
2026-07-03 19:36 | 2026-07-03 19:36 |        257 | scripts/_test_schtasks.bat
2026-07-03 19:38 | 2026-07-03 19:38 |       1386 | scripts/_patch_schtasks_enc.py
2026-07-03 19:38 | 2026-07-03 19:38 |       1257 | scripts/_patch_ps_skill.py
2026-07-03 19:48 | 2026-07-03 19:57 |        527 | .worktrees/dev-process-monitor/logs/dev_tray/start_monitor.cmd
2026-07-03 19:48 | 2026-07-03 20:13 |      19931 | .worktrees/dev-process-monitor/logs/dev_tray/monitor.log
2026-07-03 19:53 | 2026-07-03 19:53 |        770 | .worktrees/dev-process-monitor/scripts/dev_ps_hidden.py
2026-07-03 19:55 | 2026-07-03 19:55 |        533 | scripts/_list_pythonw.py
2026-07-03 20:18 | 2026-07-03 20:18 |        169 | tmp/grok_era_files.txt
2026-07-03 20:29 | 2026-07-03 20:29 |      12509 | docs/governance/PROJECT_REPORT.md
2026-07-03 20:35 | 2026-07-03 20:35 |       1747 | scripts/_gen_report_appendix.py
```

---

*Приложение E регенерируется: `python scripts/_gen_report_appendix.py`*
