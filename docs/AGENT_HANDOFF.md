# Handoff: что сделано в проекте и где смотреть (для следующего агента)

> Цель этого файла — чтобы новый агент/разработчик за 10–15 минут понял текущее состояние проекта, решения и где искать причины ошибок.

## 0) Главные правила
- Основные правила для агентов/разработчиков: `docs/AGENTS.md` (корень проекта).
- Проверенные команды запуска/диагностики: `docs/DEBUG.md`.

## 0) Важно про секреты
- **Нельзя коммитить**: `.env`, `github_ssh_*`, папки `logs/`, `data/`, `tmp/`, `.venv/`.
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
- Активная разработка: `feature/*`; актуальную ветку всегда проверяйте командой `git status -sb`.

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

Проверка: запустить `python -m app.entrypoints.bot`, отправить 1 файл и убедиться, что появляется явная клавиатура "Обработать/Добавить ещё"; отправить 2 файла — увидеть выбор "Объединить/Раздельно".

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
- Synced docs: updated `docs/AGENTS.md`, `docs/DEV_SETUP.md`, `docs/ARCHITECTURE.md`, `docs/TESTCASES.md` to match current UX and run config usage.

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
  - обновлены `app/bot/manager.py`, `docs/DEBUG.md`, `docs/README.md`, `docs/TODO.md`.
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
  - обновлены `app/api.py`, `app/tasks.py`, `app/entrypoints/bot.py`, `app/entrypoints/worker.py`, `app/config.py`, `config/.env.example`;
  - обновлены `docs/DEBUG.md`, `docs/DEV_SETUP.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `docs/TODO.md`;
  - удалена мёртвая папка `app/logs/`.
- Поведение:
  - backend/worker/bot пишут логи через единый observability-слой в `logs/*.log` + общий `logs/errors.log`;
  - включены алерты в `logs/alerts.jsonl` (c cooldown и optional Telegram через `ALERTS_TELEGRAM_CHAT_ID`);
  - включен мониторинг времени/ошибок в `logs/metrics.jsonl`, доступен `/metrics/summary` и `scripts/metrics_report.py`;
  - все чекбоксы Этапа 4 отмечены как выполненные в `docs/TODO.md`;
  - тексты пользовательских сообщений вынесены в отдельный каталог `docs/BOT_MESSAGE_CATALOG.md` (обновляется скриптом).
- Быстрая проверка:
  - `python -m compileall app\observability.py app\api.py app\\tasks.py app\\entrypoints\\bot.py app\\entrypoints\\worker.py scripts\metrics_report.py scripts\export_user_messages.py`
  - `curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"`
  - `python scripts\metrics_report.py --minutes 60`
  - `python scripts\export_user_messages.py`

## 14) Local iiko server docs cache (2026-03-11)
- Files:
  - added `iiko_server_docs/SOURCES.txt` (source URL list);
  - added `iiko_server_docs/README.md` (how to refresh/search cache);
  - added `scripts/cache_iiko_server_docs.ps1` (download HTML snapshots);
  - added `scripts/search_iiko_server_docs.ps1` (local grep helper).
- Behavior:
  - docs are cached in `iiko_server_docs/*.html` with summary in `INDEX.md`;
  - hash routes like `.../#!api-documentations/iikoserver-api` are resolved to direct fetch URLs.
- Quick check:
  - `powershell -ExecutionPolicy Bypass -File scripts\cache_iiko_server_docs.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts\search_iiko_server_docs.ps1 -Pattern "iikoserver"`

## 15) Stage 3 block: guardrails and OCR quality (2026-03-11)
- Files:
  - updated `app/services/pipeline.py` (stronger OCR/LLM guardrails, image preprocessing, schema alignment);
  - updated `app/utils/user_messages.py` (richer invoice output fields and request code in final message);
  - updated `requirements.txt` (added `pytesseract`);
  - updated `docs/BOT_COMMAND_MATRIX.md` (current UX behavior notes).
- Behavior:
  - pipeline now detects typical garbage LLM outputs more aggressively (repeats/zeros/header leakage/repeated numeric columns);
  - image flow includes OCR hints and retries/fallbacks to improve extraction stability on table invoices;
  - user-facing invoice message includes mass, VAT details and short request code.
- Quick check:
  - `python -m compileall app\services\pipeline.py app\utils\user_messages.py`
  - send one invoice image/pdf through bot and verify final message contains VAT/mass fields and request code;
  - verify no regressions in `/process` and worker task completion logs.

## 16) Repo hygiene sync (2026-03-11)
- Files:
  - added `scripts/cache_iiko_server_docs.ps1`;
  - added `scripts/search_iiko_server_docs.ps1`;
  - updated `docs/AGENT_HANDOFF.md`.
- Behavior:
  - local iiko docs scripts are now present in this branch (no doc/code drift);
  - both scripts resolve relative paths from repo root (`iiko_server_docs/...`) and work regardless of current shell directory;
  - for current active branch always trust `git status -sb` instead of static text in this file.
- Quick check:
  - `powershell -ExecutionPolicy Bypass -File scripts\search_iiko_server_docs.ps1 -Pattern "iikoserver"`

## 17) Branch transition: Stage3 guardrails closed (2026-03-11)
- Decision:
  - `feature/todo-stage3-guardrails-ux` is considered complete by branch scope (guardrails + OCR quality + docs/tools sync).
  - Remaining broader TODO items (template parsers, hybrid parser, cost aggregates) stay in backlog for the next stage.
- Next work branch:
  - `feature/stage6-iiko-import-readiness` (focus: iiko field mapping, units normalization, import path).
- Quick check:
  - `git branch -vv`
  - `git status -sb`

## 18) iikoServer mapping + ecosystem analysis docs (2026-03-11)
- Files:
  - added `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`;
  - added `docs/exp/BUSINESS_INTEGRATIONS_PLAN.md`;
  - added `docs/exp/IIKO_STORE_CATALOG.md`;
  - updated `docs/TODO.md` (Stage 8 checklist).
- Behavior/decisions:
  - documented complete incoming invoice field mapping for `iikoServer` (`incomingInvoiceDto` + `incomingInvoiceItemDto`), including required fields, optional fields, read-only fields, VAT and unit conversion rules;
  - documented migration strategy from current Playwright UI upload to API-first path with idempotency and safe posting policy (`NEW` draft by default, optional auto-post);
  - captured live catalog snapshot from `store.iiko.ru` and `store.iiko.ru/connectors` for product/partner landscape planning;
  - created business roadmap focused on non-trivial value modules (supplier reliability, margin drift control, claim automation, cross-store procurement optimization).
- Quick check:
  - open and review `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`;
  - open and review `docs/exp/BUSINESS_INTEGRATIONS_PLAN.md`;
  - open and review `docs/exp/IIKO_STORE_CATALOG.md`;
  - run `git status -sb` to confirm only docs were changed.

## 19) New chat entrypoint (2026-03-12)
- File:
  - added `docs/START_HERE_NEW_CHAT.md` (single-page onboarding entrypoint).
- Purpose:
  - gives a strict reading order and immediate run commands for fast context restore in a fresh chat;
  - points directly to Stage 8 target docs and next implementation tasks.
- Quick check:
  - open `docs/START_HERE_NEW_CHAT.md`;
  - execute `git status -sb`.

## 20) Termux/Tailscale phone link sync (2026-03-16)
- Files:
  - added `scripts/termux_ssh_toolkit/windows/11_tailscale_phone_link.ps1`;
  - updated `scripts/termux_ssh_toolkit/windows/03_show_connection_info.ps1` (includes Tailscale info + preferred LAN IP selection);
  - updated `docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md` (Tailscale mode section);
  - updated `scripts/termux_ssh_toolkit/README.md` and `local_setup/termux_ssh/README.md` with Tailscale usage path.
- Behavior:
  - Windows helper now reports Tailscale install/login state and gives ready-to-run Termux SSH command;
  - connection info script now prefers `192.168.x.x` for LAN and also prints Tailscale SSH endpoint;
  - you can switch Termux toolkit to Tailscale route via `wsetip <tailscale_ip>` and keep existing `wssh/wgo/wvibe` workflow unchanged.
- Quick check:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\11_tailscale_phone_link.ps1`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\03_show_connection_info.ps1`

## 21) Termux mailbox + encoding hardening (2026-03-17, from dump sync)
- Files/docs:
  - added `docs/TERMUX_MAILBOX_STABLE_WORKFLOW_2026-03-16.md`;
  - updated `docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md` and `docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md` with `wmailbox`/clipboard/tutor/phone flows;
  - wrapper behavior reflected in `scripts/termux_ssh_toolkit/termux/02_add_aliases.sh` and `scripts/termux_ssh_toolkit/windows/06_run_vibe_wrapper.ps1`.
- Behavior:
  - stabilized mailbox return path (`wmailbox pull` / `wmailbox pullclip`, aliases `wpaste`, `wclip`);
  - fixed recurring mojibake class by enforcing UTF-8 prelude for remote PowerShell sessions (`InputEncoding/OutputEncoding` + `chcp 65001`) and keeping command transport base64-safe;
  - documented non-interactive SSH defaults for stable pullclip path (`BatchMode`, `NumberOfPasswordPrompts=0`, `StrictHostKeyChecking=accept-new`);
  - captured `wvibe api` model fallback rule: when active model is unavailable (e.g., `devstral-2`), wrapper falls back to `labs-leanstral-2603`;
  - `scripts/termux_ssh_toolkit/windows/06_run_vibe_wrapper.ps1` now auto-normalizes legacy invalid `active_model="devstral-2"` in `%USERPROFILE%\.vibe\config.toml` to `labs-leanstral-2603` before wrapper start/reconnect flow.
- Quick check:
  - in Termux: `source ~/.bashrc`, then `whelp`, `wmailbox pullclip`, `wvibe doctor`;
  - optional API check: `wvibe api "Reply exactly: OK"` (if `MISTRAL_API_KEY` is configured).

## 22) Strict delivery policy for command blocks (2026-03-17)
- Files:
  - updated `docs/AGENTS.md`, `docs/TERMUX_MAILBOX_STABLE_WORKFLOW_2026-03-16.md`, `docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md`, `docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md`, `VIBE.md`.
- Behavior:
  - executable command blocks for operator are delivered via mailbox channel only;
  - chat is reserved for context, decisions, status, and results (without runnable command packs).

## 23) Termux alias installer EOF fix (2026-03-17)
- File:
  - updated `scripts/termux_ssh_toolkit/termux/02_add_aliases.sh`.
- Behavior:
  - fixed heredoc delimiter collision in `.bashrc` block generation (`EOF` -> unique `__WINDEV_BASH_BLOCK__`);
  - prevents truncated `~/.bashrc` toolkit block and errors like `delimited by end-of-file` / `unexpected EOF` after `source ~/.bashrc`.

## 24) `whelp` source unification (2026-03-17)
- Files:
  - updated `scripts/termux_ssh_toolkit/shared/whelp_ru.txt`;
  - updated `scripts/termux_ssh_toolkit/termux/02_add_aliases.sh`.
- Behavior:
  - `whelp` content is now sourced from one shared file for both Termux and Windows dispatcher paths;
  - moved clipboard shortcuts section into shared `whelp_ru.txt` and removed Termux-only appended block, so help output is consistent across entrypoints.

## 25) Termux toolkit bootstrap refactor: ~/.bashrc в†’ ~/.config/windev/toolkit.sh (2026-03-18)

### Root cause: heredoc EOF collision + monolithic block

**Problem:** 
- `02_add_aliases.sh` embedded 1300+ lines of functions in `~/.bashrc` via single heredoc with delimiter `__WINDEV_BASH_BLOCK__`
- If any line in the block matched or contained the delimiter, heredoc terminated early в†’ `~/.bashrc` left with unclosed blocks в†’ `unexpected EOF` on `source ~/.bashrc`
- No syntax validation before installation
- Reinstall could leave broken state (idempotency not guaranteed)
- Functions executed at source time (no silent loading)

**Impact:**
- Users report: "source ~/.bashrc gives: unexpected EOF"
- Repeated toolkit reinstall leaves `~/.bashrc` corrupted
- Debugging difficult (error could be anywhere in 1300-line heredoc)

### Solution: Atomic, separate-file architecture

**New structure:**
```
~/.bashrc (minimal bootstrap, ~15 lines)
  в†“ sources
~/.config/windev/toolkit.sh (generated, validated, atomic)
```

**How it works:**
1. `02_add_aliases_v2.sh` reads `scripts/termux_ssh_toolkit/shared/toolkit_functions.sh` template
2. Substitutes variables (`{{WIN_HOST}}`, `{{WIN_USER}}`, etc.)
3. Writes to temp file
4. Validates with `bash -n temp_toolkit`
5. Creates backup of existing toolkit
6. **Atomically moves** temp в†’ `~/.config/windev/toolkit.sh`
7. Updates `~/.bashrc` with minimal bootstrap (if not present)

**Files changed/added:**
- Added `scripts/termux_ssh_toolkit/shared/toolkit_functions.sh` (template for all toolkit functions)
- Added `scripts/termux_ssh_toolkit/termux/02_add_aliases_v2.sh` (new atomic installer)
- Updated `scripts/termux_ssh_toolkit/termux/install.sh` (calls v2 by default, fallback to --legacy)
- Updated `~/.bashrc` bootstrap (minimal sourcing of toolkit.sh)
- Added `docs/BASHRC_REFACTOR_GUIDE.md` (migration guide for operators)
- Deprecated `scripts/termux_ssh_toolkit/termux/02_add_aliases.sh` (still works with --legacy flag)

### Behavior changes

**For user (operator):**

Before:
```bash
bash scripts/termux_ssh_toolkit/termux/install.sh ...
# Installs 1300 lines directly into ~/.bashrc
# Risk: ~/.bashrc left broken if heredoc delimiter collision
```

After:
```bash
bash scripts/termux_ssh_toolkit/termux/install.sh ...
# Installs toolkit atomically to ~/.config/windev/toolkit.sh
# Bootstrap sourcing added to ~/.bashrc (if not present)
# Syntax checked before installation
# Safe to rerun multiple times
```

**For developers:**

- Toolkit functions are now in separate file (easy to review, syntax-check, test)
- Bootstrap is minimal (~15 lines, no hidden blocks)
- Can validate before installation: `bash -n ~/.config/windev/toolkit.sh`
- Easy to revert: `cp ~/.config/windev/toolkit.sh.bak ~/.config/windev/toolkit.sh`

**For wring specifically:**

Improved to explicitly separate command exit code from mailbox push status:

```bash
# Old: mixed concerns, ambiguous return code
if cat "$out_file" | wmailbox inbox; then
  echo "[ok] wring output pushed to inbox."
else
  echo "[error] failed to push wring output to inbox."
  return 70  # arbitrary code
fi
return "$run_rc"  # which status do we actually care about?

# New: clear separation, explicit status
if cat "$out_file" | wmailbox inbox; then
  echo "[ok] wring: command exit code $run_rc, output pushed to inbox."
else
  echo "[error] wring: command exit code $run_rc, failed to push output to inbox."
fi
return "$run_rc"  # always return command's exit code
```

### Quick check (validation)

For operator:
```bash
# 1) New install
bash scripts/termux_ssh_toolkit/termux/install.sh --win-host 192.168.1.100 --skip-keygen

# 2) Source and verify no output/errors
source ~/.bashrc
# (should produce no output)

# 3) Check functions available
command -v wmailbox whelp wstatus wrunbox wring
# (all should exist)

# 4) Verify whelp works
whelp | head -20

# 5) Idempotency: rerun 2-3 times
bash scripts/termux_ssh_toolkit/termux/install.sh --win-host 192.168.1.100 --skip-keygen
source ~/.bashrc
# (should be stable each time)

# 6) E2E mailbox
wmailbox status
```

For developer:
```bash
# 1) Syntax validation
bash -n ~/.bashrc
bash -n ~/.config/windev/toolkit.sh

# 2) Template expansion (check substitutions)
head -20 ~/.config/windev/toolkit.sh
# Should show actual IPs/usernames, not {{placeholders}}

# 3) Version tracking
cat ~/.config/windev/.version
# Should show install timestamp and host info
```

### Remaining risks & mitigation

**Risk 1: Old ~/.bashrc with 1300-line block not cleaned up**
- Mitigation: `02_add_aliases_v2.sh` explicitly removes old block before adding bootstrap

**Risk 2: ~/.config/windev/ inaccessible (XDG_CONFIG_HOME mismatch)**
- Mitigation: Bootstrap uses `${XDG_CONFIG_HOME:-$HOME/.config}`, respects env var

**Risk 3: No backup if reinstall fails**
- Mitigation: `02_add_aliases_v2.sh` creates `.bak` files before overwriting

**Risk 4: Operator doesn't know how to debug if toolkit.sh broken**
- Mitigation: `docs/BASHRC_REFACTOR_GUIDE.md` includes troubleshooting section + recovery steps

### Migration path (for existing users)

Users with old installations:
```bash
cd ~/iikoinvoicebot
git pull --ff-only

bash scripts/termux_ssh_toolkit/termux/install.sh \
  --win-user MiBookPro \
  --win-host 192.168.1.100 \
  --skip-keygen

source ~/.bashrc
whelp  # test
```

Automatic:
- Old monolithic block is removed
- New bootstrap is added
- toolkit.sh is generated and validated
- Backups created in case of rollback

### Documentation updated

- Added `docs/BASHRC_REFACTOR_GUIDE.md` (operator migration + troubleshooting)
- Updated `docs/AGENT_HANDOFF.md` (this section)
- Updated `docs/TERMUX_MAILBOX_STABLE_WORKFLOW_2026-03-16.md` (reference to new architecture)
- Updated `docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md` (installer v2 notes)
- Updated `docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md` (toolkit.sh location)
- Updated `scripts/termux_ssh_toolkit/README.md` (architecture overview)

---

### Implementation checklist

- [x] Create `toolkit_functions.sh` template
- [x] Create `02_add_aliases_v2.sh` (atomic installer)
- [x] Update `install.sh` (call v2 by default)
- [x] Create `BASHRC_REFACTOR_GUIDE.md`
- [x] Update this section in `AGENT_HANDOFF.md`
- [ ] Migrate repo files (copy templates to actual location)
- [ ] Test syntax: `bash -n toolkit.sh`
- [ ] Test idempotency (rerun install 2-3 times)
- [ ] Test e2e (wmailbox, whelp, wstatus)
- [ ] Document any edge cases encountered


