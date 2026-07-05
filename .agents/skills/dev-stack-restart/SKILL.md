---
name: dev-stack-restart
description: Fast start/stop/restart PyCharm dev stack 1 (backend), 2 (worker), 5 (MAX bot), 8 (VPN). Use when user says "подними 1 2 5", "подними 1 2 5 8", "перезапусти стек", "restart backend worker max", "dev stack", or agent needs to launch invoice dev processes. NEVER use raw PowerShell uvicorn one-liners or manual `python -m …` in agent shell.
---

# Dev stack restart (1 / 2 / 5 / 8)

## Why agent launches were slow

The agent shell wraps commands as `(cd REPO ; <cmd>)`. PowerShell 5.x **breaks** when `<cmd>` contains `--port 8000` — the closing `)` is parsed as end of the group → instant `ParserError`, wasted retries, ~1–2 min lost.

**Rule:** one command only — `dev_stack_ctl.py`. No `Set-Location; uvicorn ...`, no `&&` in PowerShell, no manual `python -m …` bypass.

## Canonical commands

From repo root (`C:\Users\MiBookPro\PycharmProjects\PythonProject`):

```text
.venv\Scripts\python.exe scripts\dev_stack_ctl.py restart
.venv\Scripts\python.exe scripts\dev_stack_ctl.py restart --only 1,2,5,8
.venv\Scripts\python.exe scripts\dev_stack_ctl.py status
.venv\Scripts\python.exe scripts\dev_stack_ctl.py stop
.venv\Scripts\python.exe scripts\dev_stack_ctl.py start --only 1,2
```

PowerShell wrapper (same behavior):

```powershell
.\scripts\dev_stack_ctl.ps1 restart
.\scripts\dev_stack_ctl.ps1 restart -Only 1,2,5,8
```

**Agent shell:** always use **cmd /c** wrapper (PowerShell `(cd ; …)` breaks on paths/flags):

```text
cmd /c "cd /d C:\Users\MiBookPro\PycharmProjects\PythonProject && .venv\Scripts\python.exe scripts\dev_stack_ctl.py restart --only 1,2,5,8"
```

Map user request → `--only`:
- `подними 1 2 5` → `--only 1,2,5`
- `подними 1 2 5 8` → `--only 1,2,5,8`

## PyCharm run configs (source of truth)

| # | Name | Command |
|---|------|---------|
| 1 | backend | `uvicorn app.api:app --host 127.0.0.1 --port 8000` |
| 2 | worker | `app/entrypoints/worker.py` |
| 5 | max invoice bot | `python -m experiments.max_invoice_bot` |
| 0 | all TG | `scripts/dev_run_all.py` — **not** MAX; use ctl for 5 |
| 8 | vpn | `scripts/ensure_sotaocr_vpn.ps1` (managed by ctl when in `--only`) |
| 9 | tray monitor | worktree `dev-process-monitor` — **not** in ctl; use `run_dev_process_monitor.ps1` (schtasks) |

Files: `.idea/runConfigurations/1__backend.xml`, `2__worker.xml`, `5__max_invoice_bot.xml`.

## Workflow

1. `dev_stack_ctl.py status` — if already 1/2/5 OK (and 8 if requested), report and skip.
2. `dev_stack_ctl.py restart --only …` (or `start` if user said "подними" and nothing runs).
3. `dev_stack_ctl.py status` — confirm health **5–10 s after start** (schtasks launch needs a moment).
4. Optional: probe from worktree — `scripts/dev_process_probe.py` (expects 1/2/5/8).

Logs: `logs/dev_stack/1.log`, `2.log`, `5.log`.

## Do not

- Start uvicorn/worker/MAX bot manually via `python -m …` in agent shell — children die when the agent job ends; ctl uses `schtasks /run` to escape the job.
- Start uvicorn via PowerShell one-liner with `--host` / `--port` inside agent `(cd ; …)` wrapper.
- Use `dev_run_all.py` when user asked for **MAX** (5) — it starts Telegram bot (3).
- Kill tray monitor (9) unless user asks.
- Start tray via `python.exe dev_process_monitor.py` in agent terminal — dies when terminal/job ends; use worktree `scripts/run_dev_process_monitor.ps1`.
- Run `ensure_sotaocr_vpn.ps1` separately when 8 is in the request — ctl handles it.

## Verify success

- `http://127.0.0.1:8000/health` → 200
- `status` shows `1: OK`, `2: OK PID …`, `5: OK PID …`, `8: OK` (when requested)
- Target: **< 20 s** for full restart on warm machine

## Known fix (2026-07)

Agent shells use Windows **job objects** — `Popen`, `start /B`, and `Start-Process` children all died when ctl exited. Fixed: ctl writes `logs/dev_stack/start_*.cmd` and launches via **`schtasks /create` + `/run`** (task runs outside the agent job). PyCharm manual run still works as before.
