# Start Here (New Chat)

Короткая точка входа в проект после хард-роллбэка от Termux/Vibe-периферии.

## 1) Прочитать в этом порядке (5-10 минут)
1. `docs/AGENT_HANDOFF.md`
2. `docs/TODO.md`
3. `docs/DEBUG.md`
4. `docs/ARCHITECTURE.md`
5. `docs/README.md`

## 2) Текущий фокус
- Stage 8.1: первый end-to-end импорт в iiko RMS demo stand.
- Закрытие продуктовых рисков:
  - персистентный runtime-state бота;
  - защищенное хранение credential'ов;
  - профиль масштабирования worker/очереди.

## 3) Runtime entrypoints
- Backend: `app.entrypoints.main`
- Worker: `app.entrypoints.worker`
- Bot: `app.entrypoints.bot`

## 4) Быстрые команды локальной проверки
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m app.entrypoints.worker
.\.venv\Scripts\python.exe -m app.entrypoints.bot
.\.venv\Scripts\python.exe scripts\dev_status.py
```

## 5) Git hygiene
```powershell
git status -sb
git branch -vv
```
