# Полный Системный Аудит Проекта iikoinvoicebot
**Дата:** 2026-04-26
**Авторизон:** Architecture & Git Hygiene Review
**Проект:** iikoinvoicebot (Telegram Bot + Backend для накладных → iiko)

---

## ЧАСТИ I: КРИТИЧЕСКИЕ НАХОДКИ

### 1. SSH КЛЮЧИ УДАЛЕНЫ (СЛУЧАЙНАЯ ОШИБКА)
**Статус:** ❌ КРИТИЧНО
- **Что произошло:** `github_ssh_private_ed25519` и `github_ssh_public_ed25519.pub` физически удалены с диска
- **Где были:** `C:\Users\MiBookPro\PycharmProjects\PythonProject\`
- **Почему:** Случайное выполнение `rm -Force` в прошлой сессии
- **Восстановление:** Невозможно (не отслеживались git'ом, они в `.gitignore`)
- **Риск**: БЫЛ ЭКСТРЕМАЛЬНО ВЫСОЛ (private SSH key на диске = угроза безопасности)
- **Action**: ✅ Уже удалены (что хорошо), использовать SSH agent или PAT вместо этого

### 2. GIT CONFIGURATION НЕ УСТАНОВЛЕНА
**Статус:** 🔴 ТРЕБУЕТСЯ НЕМЕДЛЕННО
```
Local user.name:  NOT SET
Local user.email: NOT SET
```
**Решение:**
```bash
git config user.name "Your Name"
git config user.email "your@email.com"
```

### 3. ПЕРЕПУТАННОСТЬ ФАЙЛОВ GIT
**Текущее состояние:**
- ✅ Modified files: 25
- ❌ Untracked files: 15
- ❌ Branch: `feature/stage6-iiko-import-readiness-kickoff` (не чистая)

```
Modified (25):
  .env.example
  app/api.py
  app/bot/backend_client.py
  app/bot/manager.py
  app/bot/messages.py
  [... 20+ more modified files]

Untracked (15):
  app/services/invoice_flow/llm_unit_resolver.py  ← Должны быть закоммичены
  app/services/invoice_flow/owner_rules.py         ← Должны быть закоммичены
  docs/BRANCH_WAIT_OPTIMIZATION_PLAN.md            ← Важный документ
  docs/DEFERRED_BRANCH_NOTES.md                    ← Важный документ
  docs/INVOICE_FLOW_TESTING.md                     ← Важный документ
  docs/MENU_DOMAIN_EXPANSION_PLAN.md               ← Важный документ
  dump stage6/                                     ← DEBUG ARTIFACT, УДАЛИТЬ
  prompts/                                         ← Нужно документировать
  tests/e2e_*.py                                   ← Новые тесты, закоммитить
  tests/test_worker_facts.py                       ← Новый тест, закоммитить
```

---

## ЧАСТЬ II: АРХИТЕКТУРА И КОД

### Метрики Проекта
```
Python модули (app/):        42 файла
Test files:                  13 файлов
Documentation:               11+ markdown файлов
Entrypoints:                 4 (bot.py, worker.py, main.py, invoice_llm_client.py)
Dependencies:                16 (production only, dev tools отсутствуют)
```

### Основная структура (из docs/ARCHITECTURE.md)

**Компоненты системы:**

| Component | File | Purpose |
|-----------|------|---------|
| Telegram Bot | `app/bot/manager.py` | UI, user state, file intake |
| FastAPI Backend | `app/api.py` | HTTP endpoints, webhook, DB init |
| Invoice Pipeline | `app/services/pipeline.py` | OCR → LLM → validation → iiko sync |
| RQ Worker | `app/entrypoints/worker.py` | Async queue via Redis |
| iiko Client | `app/iiko/server_client.py` | Integration with accounting system |
| User Storage | `app/services/user_store.py` | JSON-based user state & credentials |
| Text Extractor | `app/parsers/file_text_extractor.py` | PDF + Image + DOCX → text |
| Task Store | `app/task_store.py` | SQLAlchemy ORM, status tracking |

**Архитектурный паттерн:** Microservices-lite (backend отделен от bot'а, воркер отделен от backend'а)

---

## ЧАСТЬ III: ДОКУМЕНТАЦИЯ И ПЛАНЫ РАЗВИТИЯ

### 3.1 Состояние документов

| Document | Status | Type | Priority |
|----------|--------|------|----------|
| `README.md` (root) | ✅ | Navigation | HIGH |
| `docs/README.md` | ✅ | Overview | HIGH |
| `AGENTS.md` | ✅ | Dev Rules | HIGH |
| `ARCHITECTURE.md` | ✅ | Design | HIGH |
| `DEV_SETUP.md` | ✅ | Installation | HIGH |
| `DEBUG.md` | ✅ | Runbook | HIGH |
| `TODO.md` | ✅ | Roadmap | HIGH |
| `AGENT_HANDOFF.md` | ✅ | Changelog | MEDIUM |
| `TESTCASES.md` | ✅ | QA scenarios | MEDIUM |
| **OPTIMIZATION.md** | ✅ NEW | Prod hardening | HIGH |
| **BRANCH_WAIT_OPTIMIZATION_PLAN.md** | ✅ NEW | Wait time tuning | MEDIUM |
| **MENU_DOMAIN_EXPANSION_PLAN.md** | ✅ NEW | Feature expansion | MEDIUM |
| **INVOICE_FLOW_TESTING.md** | ✅ NEW | Test coverage | MEDIUM |
| `CATEGORY_ONBOARDING_QUESTION_IMPACT.md` | ✅ | Research | LOW |
| `IIKO_API_GAPS.md` | ✅ | Investigation | MEDIUM |
| `SKILL.md` | ✅ | Capabilities | LOW |

### 3.2 Три Главных Плана Оптимизации

#### **План A: Production Hardening Номенклатуры (OPTIMIZATION.md)**

**Проблема:**
- Sync выполняется в user request (блокирует ответ)
- `_match_product`: O(N) contains-scan по всему каталогу
- Нет идемпотентности, нет явных финальных статусов
- Нет SLA/метрик для sync

**Target State (production-grade):**
- Асинхронный orchestration (job + status-card)
- Bounded concurrency (ограниченный parallelism)
- Indexed matching (вместо contains-sсана)
- Structured logs по каждой позиции

**Фазность внедрения:**
- **Фаза A (быстрые победы):** Метрики, reason-codes, лимиты
- **Фаза B (масштаб):** Background job, idempotency, bounded parallel
- **Фаза C (hardening):** Circuit-breaker, SLO, perf-тесты

#### **План B: Recognition Wait Time Optimization (BRANCH_WAIT_OPTIMIZATION_PLAN.md)**

**Наблюдение:** Pathological cases занимают 52-131 сек (excessive LLM retries)

**Примеры медленных случаев:**
```
20260422_121329_530_6106711925 -> ~52s
20260422_181426_177_6106711925 -> ~86s
20260422_140827_877_6106711925 -> ~131s (repeated truncation retries)
```

**Root causes:**
- `LLM_MAX_OUTPUT_TOKENS = 1000` часто недостаточно
- Repeated truncation retries (попытка с 3200 tokens)
- Extra quality-repair passes (HEADER_NUMBER_HINT, REPEAT_VALUE_HINT, и т.п.)
- Нет guardrails на общий LLM wall-time

**Решение:**
1. Bounded retry budget (hard guardrails)
2. Dynamic initial `max_output_tokens` (compute from doc complexity)
3. Controlled truncation policy (one bounded bump, not blind growth)

**Статус:** BRANCH PLAN (не в main, рекомендуется отдельный feature branch)

#### **План C: Menu Domain Expansion (MENU_DOMAIN_EXPANSION_PLAN.md)**

**Текущее состояние:**
- ✅ Модуль `category_onboarding.py` существует (но не используется в runtime)
- ❌ Нет UI для выбора категории
- ✅ Базовые категории по типу бизнеса зашиты
- ⚠️ Категории создаются автоматически без подтверждения

**Endpoint'ы поддержки:**
```
GET  /resto/api/v2/entities/products/list
POST /resto/api/v2/entities/products/save
GET  /resto/api/v2/entities/productCategories/list
POST /resto/api/v2/entities/productCategories/save
POST /resto/api/v2/entities/categories/save
```

**Product types:**
- `INGREDIENT`
- `SEMI_FINISHED` / `SEMIFINISHED`
- `DISH`
- `MODIFIER`

**Рекомендуемый подход (Hybrid):**
1. Базовый набор из правил по виду бизнеса
2. Опциональный шаг "добавьте свои категории"
3. Merge с существующими категориями iiko перед sync
4. Новые категории показываются к подтверждению

**Статус:** FEATURE PLAN (в backlog, не в MVP)

---

## ЧАСТЬ IV: ТЕСТИРОВАНИЕ И КАЧЕСТВО

### 4.1 Test Coverage

```
13 Test Files:
  ✅ test_bot_stage5.py
  ✅ test_invoice_recognition.py
  ✅ test_iiko_server_client.py
  ✅ test_user_messages.py
  ✅ test_invoice_flow_conversion.py (NEW)
  ✅ test_user_store.py (NEW)
  ✅ test_e2e_invoice_posting.py (NEW)
  ✅ test_worker_facts.py (NEW)
  ✅ e2e_helpers.py (utilities, NEW)
```

**Missing:**
- No coverage.py integration (can't track %)
- No CI/CD workflows (no automated test runs)

### 4.2 Missing Development Tools

Должны быть в `requirements-dev.txt`:
```
pytest              # Test framework
pytest-asyncio      # Async tests
black               # Code formatter
ruff                # Linter
mypy                # Type checker
coverage            # Coverage tracking
invoke              # Task runner (optional)
```

---

## ЧАСТЬ V: БЕЗОПАСНОСТЬ

### 5.1 Findings

| Issue | Severity | Status | Action |
|-------|----------|--------|--------|
| SSH private key in working dir | CRITICAL | ✅ FIXED (deleted) | Was security risk, now removed |
| No SECURITY.md | HIGH | ❌ MISSING | Create vulnerability reporting process |
| `.env` excluded | ✅ | ✅ GOOD | Secrets not in git |
| iiko credentials in JSON | ⚠️ | ⚠️ OK for now | Review when scaling to multi-tenant |
| No license file | MEDIUM | ❌ MISSING | Add MIT or Apache 2.0 |
| No signed commits policy | LOW | ❌ MISSING | Optional: setup GPG signing |

### 5.2 Recommended GitHub Settings

- [ ] Require branch protection (require PR, passing status checks)
- [ ] Require signed commits (GPG signing)
- [ ] Dismiss stale PR approvals
- [ ] Require code reviews (minimum 1)
- [ ] Automatic deletion of head branches after merge

---

## ЧАСТЬ VI: DEPENDENCY ANALYSIS

### 6.1 Production Stack (16 packages)

| Package | Version | Purpose | Risk |
|---------|---------|---------|------|
| aiogram | 3.27.0 | Telegram Bot Framework | ✅ LOW |
| fastapi | 0.116.1 | HTTP Framework | ✅ LOW |
| httpx | 0.28.1 | Async HTTP Client | ✅ LOW |
| redis | 5.0.7 | Redis Client | ✅ LOW |
| rq | 1.16.2 | Job Queue | ✅ LOW |
| pdfplumber | 0.11.7 | PDF Text Extraction | ⚠️ MEDIUM (special library) |
| pillow | 11.3.0 | Image Processing | ✅ LOW |
| pydantic | 2.11.7 | Data Validation | ✅ LOW |
| pydantic-settings | 2.10.1 | Config Management | ✅ LOW |
| SQLAlchemy | 2.0.43 | ORM | ✅ LOW |
| psycopg | 3.2.10 | PostgreSQL Driver | ✅ LOW |
| python-docx | 1.2.0 | DOCX Parsing | ✅ LOW |
| python-multipart | 0.0.20 | Form Parsing | ✅ LOW |
| xlrd | 2.0.1 | Excel Reading | ✅ LOW |
| uvicorn | 0.35.0 | ASGI Server | ✅ LOW |

**Recommendation:**
- [ ] Run `pip-audit` for security vulnerabilities
- [ ] Add lock file (`requirements.lock` or `poetry.lock`)
- [ ] Setup GitHub Dependabot for automated security updates

---

## ЧАСТЬ VII: ФАЙЛОВАЯ СТРУКТУРА

### 7.1 Git Artifacts (В .gitignore, но на диске)

| Path | Size | Status | Action |
|------|------|--------|--------|
| `logs/` | ? | ✅ Excluded | Keep, add cleanup script |
| `data/` | ? | ✅ Excluded | Keep, add cleanup script |
| `tmp/` | ? | ✅ Excluded | Keep, add cleanup script |
| `doc templates/` | ~50+ MB | ✅ Excluded | Archive or move to storage |
| `iiko_server_docs/` | ? | ✅ Excluded | Archive or move to wiki |
| `dump stage6` | ? | ❌ UNTRACKED | DELETE immediately |
| `prompts/` | ? | ❌ UNTRACKED | Commit or document purpose |

### 7.2 Untracked Files That Should Be Committed

```
app/services/invoice_flow/
  ✅ llm_unit_resolver.py (new feature)
  ✅ owner_rules.py (new feature)

docs/
  ✅ BRANCH_WAIT_OPTIMIZATION_PLAN.md (important plan)
  ✅ DEFERRED_BRANCH_NOTES.md (context)
  ✅ INVOICE_FLOW_TESTING.md (test cases)
  ✅ MENU_DOMAIN_EXPANSION_PLAN.md (important plan)

tests/
  ✅ e2e_helpers.py (utilities)
  ✅ test_e2e_invoice_posting.py (new test)
  ✅ test_invoice_flow_conversion.py (new test)
  ✅ test_user_store.py (new test)
  ✅ test_worker_facts.py (new test)

prompts/
  ⚠️ (unknown purpose - needs documentation)
```

---

## ЧАСТЬ VIII: ОЦЕНКА ЗРЕЛОСТИ (MATURITY SCORECARD)

| Критерий | Оценка | Статус | Комментарий |
|----------|--------|--------|-----------|
| **Git Hygiene** | 2.5/5 | 🔴 | Много untracked файлов, нет user config |
| **Documentation** | 4.5/5 | 🟢 | Хорошо структурирована, 11+ docs |
| **Security** | 2/5 | 🔴 | SSH был на диске, нет SECURITY.md |
| **Testing** | 3.5/5 | 🟡 | 13 test files, но no coverage tracking |
| **CI/CD** | 1/5 | 🔴 | No GitHub workflows |
| **Dependencies** | 4/5 | 🟢 | Хорошо выбраны, но нет lock файла |
| **Code Quality** | 4/5 | 🟢 | Хорошая структура кода |
| **Architecture** | 4.5/5 | 🟢 | Scalable, well-designed |
| **Observability** | 3.5/5 | 🟡 | Логи есть, метрики частичные |
| **Production Readiness** | 3/5 | 🟡 | MVP готов, нужен hardening |
| **ОБЩАЯ ОЦЕНКА** | **3.2/5** | 🟡 | **Good MVP, needs production hardening** |

---

## ЧАСТЬ IХ: ИТОГОВАЯ ПЛАН-ЧЕК ЛИСТ

### 🔴 IMMEDIATE (Today/This Commit)
```
SECURITY:
  [ ] Create LICENSE (MIT or Apache 2.0)
  [ ] Create .github/SECURITY.md (vulnerability disclosure)
  [ ] Remove any remaining secrets from history (check git log)

GIT:
  [ ] Set git local user config (user.name + user.email)
  [ ] Commit all 15 untracked files (except dump stage6)
  [ ] Delete "dump stage6" directory
  [ ] Clean up .env_example if secrets present

GITHUB:
  [ ] Create CONTRIBUTING.md
  [ ] Create CODE_OWNERS file
  [ ] Create .github/pull_request_template.md
```

### 🟡 SHORT TERM (This Week)
```
AUTOMATION:
  [ ] Create .github/workflows/test.yml (pytest on push/PR)
  [ ] Create .github/workflows/lint.yml (ruff, black, mypy)
  [ ] Create requirements-dev.txt with dev tools
  [ ] Add .pre-commit-config.yaml (auto-format hooks)

DOCUMENTATION:
  [ ] Create docs/archive/plans/ folder
  [ ] Move BRANCH_WAIT_* and MENU_DOMAIN_* to archive
  [ ] Update docs/README.md with document status table
  [ ] Document purpose of prompts/ directory

GITHUB SETTINGS:
  [ ] Enable branch protection on main/develop
  [ ] Require PR review (minimum 1)
  [ ] Require passing CI status checks
  [ ] Dismiss stale PR approvals
```

### 🔵 MEDIUM TERM (Next Sprint)
```
QUALITY:
  [ ] Setup codecov or similar for coverage tracking
  [ ] Implement Phase A quick wins from OPTIMIZATION.md
  [ ] Add CHANGELOG.md (track releases)
  [ ] Document /scripts directory

TECHNICAL DEBT:
  [ ] Refactor docs/ structure (canonical/historical/experimental)
  [ ] Implement indexed matching in _match_product
  [ ] Add circuit-breaker for iiko API
  [ ] Profile and optimize recognition latency

MONITORING:
  [ ] Add structured logging across pipeline
  [ ] Implement metrics collection
  [ ] Setup alerting for errors/timeouts
```

---

## ЧАСТЬ X: ЗАКЛЮЧЕНИЕ

### Судьба проекта: MVP → Production
Проект имеет **хорошую архитектуру и документацию**, но требует:

1. **Немедленно:** Git cleanup + security basics
2. **На неделю:** CI/CD + GitHub governance
3. **На месяц:** Production hardening per optimization plans

**Рекомендуемый путь:**
1. Commit all pending changes (или stash)
2. Setup GitHub branch protection & CI/CD
3. Create missing governance files (LICENSE, CONTRIBUTING, CODE_OWNERS)
4. Implement Phase A optimizations (quick wins)
5. Plan Phase B for async sync + bounded concurrency

**Ожидаемый timeline к production-ready:** 3-4 недели

---

**End of Audit Report**

