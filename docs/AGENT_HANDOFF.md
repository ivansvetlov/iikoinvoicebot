# AGENT_HANDOFF

Обновлено: 2026-04-03

## Current state
- Проект вернулся к основному продуктовому контуру: Telegram bot + backend + worker + iiko integration.
- Termux/Vibe/operator toolkit удален из репозитория (hard rollback).
- Документация очищена от phone/ssh/mailbox workflow.

## Runtime map
- Backend: `app/entrypoints/main.py`
- Worker: `app/entrypoints/worker.py`
- Bot: `app/entrypoints/bot.py`
- Core pipeline: `app/services/pipeline.py`
- Queue execution: `app/tasks.py`

## Product focus
- Stage 8.1: первый end-to-end импорт в RMS demo stand.
- Закрыть критичные риски:
  - защищенное хранение credential'ов;
  - персистентный runtime-state бота;
  - профиль масштабирования очереди и worker.

## Key docs
- `docs/START_HERE_NEW_CHAT.md`
- `docs/TODO.md`
- `docs/DEBUG.md`
- `docs/ARCHITECTURE.md`
- `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`
- `docs/exp/IIKO_RMS_DEMO_PROFILE_2026-03-16.md`

## Quick verification
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m app.entrypoints.worker
.\.venv\Scripts\python.exe -m app.entrypoints.bot
.\.venv\Scripts\python.exe scripts\dev_status.py
```
