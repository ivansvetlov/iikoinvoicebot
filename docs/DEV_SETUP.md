# DEV_SETUP: как запускать проект локально и не убивать процессы руками

Этот файл нужен будущему себе (и другим), чтобы не устраивать зоопарк из нескольких
процессов бота/бекенда/воркера и не ловить `TelegramConflictError`.

## 1. Компоненты, которые мы запускаем локально

Проект состоит из трёх процессов:

1. **Backend (FastAPI + uvicorn)**  
   Файл входа: `app/api.py`  
   Запускается как:
   ```bash
   uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload
   ```

2. **Worker (RQ-воркер)**  
   Файл: `worker.py`  
   Берёт задачи из Redis и выполняет пайплайн.
   ```bash
   python worker.py
   ```

3. **Telegram-бот (polling)**  
   Файл: `bot.py`  
   Забирает обновления у Telegram и ходит в backend.
   ```bash
   python bot.py
   ```

> ВАЖНО: для одного `TELEGRAM_BOT_TOKEN` должен быть **только один** живой процесс `bot.py`.
> Два параллельных polling-а дают `TelegramConflictError`.

## 2. Быстрый запуск всех компонентов одной командой

> Важно: `scripts/dev_run_all.py` перед запуском бота пытается остановить другие процессы `bot.py` (в том же venv/проекте),
> чтобы не ловить `TelegramConflictError`.

Для локальной разработки можно запустить backend, worker и бота одной командой:

```powershell
.\.venv\Scripts\python.exe scripts\dev_run_all.py
```

Скрипт делает:
- стартует backend (uvicorn) и ждёт, пока `/health` начнёт отвечать;
- запускает worker (`worker.py`);
- запускает бота (`bot.py`);
- если на любом шаге ошибка (порт занят, backend не поднимается и т.п.) —
  останавливает уже запущенные процессы и печатает сообщение.

После запуска скрипта можно работать с ботом, не думая о частичных запусках.

## 3. Рекомендованный способ запуска (через PyCharm)

### Run-конфигурации
Создай в PyCharm три Run-конфигурации:

- **backend**  
  `Module name`: `uvicorn`  
  `Parameters`: `app.api:app --host 127.0.0.1 --port 8000 --reload`

- **worker**  
  `Script path`: `worker.py`

- **bot**  
  `Script path`: `bot.py`

### Правило
- Запускаем и останавливаем их **только через PyCharm**: зелёный треугольник (Run) / красный квадрат (Stop).
- Не запускаем `python bot.py`/`python worker.py` руками в терминале параллельно.

Если нужно перезапустить бота:
1. Нажать **Stop** на конфигурации `bot`.
2. Убедиться, что внизу IDE нет зелёной точки “Running”.
3. Нажать **Run** ещё раз.

## 3. Как понять, что всё работает

### Backend
```bash
curl http://127.0.0.1:8000/health
```
Ожидаем ответ:
```json
{"status":"ok"}
```

### Worker
В Run-конфигурации `worker` в логах должно быть:
```text
*** Listening on default...
```
И при новых задачах — строки `Job OK (...)`.

### Бот
В Run-конфигурации `bot` в логах должно быть:
```text
Run polling for bot @iikoinvoicebot id=... - 'iiko invoice'
```
И без постоянного спама `TelegramConflictError`.

## 4. Быстрая проверка окружения (backend/worker)

Перед тем как запускать бота, можно проверить, что backend и worker подняты:

```powershell
.\.venv\Scripts\python.exe scripts\dev_status.py
```

Скрипт не запускает процессы, а только показывает:
- доступен ли `http://127.0.0.1:8000/health` (backend)
- есть ли активные воркеры RQ (worker)

Если всё ок, а бот не отвечает — значит, проблема именно в `bot.py` (run-конфигурация).

## 5. Что делать, если всё-таки словили TelegramConflictError

Сообщение вида:
```text
Telegram server says - Conflict: terminated by other getUpdates request;
make sure that only one bot instance is running
```
означает, что где-то уже крутится другой `bot.py`.

Шаги:
1. В PyCharm закрой все Run-конфигурации `bot`, `worker`, `backend` (красный квадрат).
2. Встроенный терминал PyCharm: если запущен `python bot.py`/`python worker.py`, жми `Ctrl+C` или закрой вкладку.
3. (Опционально) в Диспетчере задач заверши `python.exe`, у которых путь вида:
   `C:\Users\MiBookPro\PycharmProjects\PythonProject\.venv\Scripts\python.exe`.
4. Затем **заново** запусти:
   - `backend`
   - `worker`
   - `bot`

## 5. Быстрые шпаргалки

### Все три процесса из терминала (если без PyCharm)

```powershell
# активируем venv
.\.venv\Scripts\activate

# Окно 1 — backend
uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload

# Окно 2 — worker
python worker.py

# Окно 3 — bot
python bot.py
```

### Проверка health и очереди

```powershell
# backend health
curl http://127.0.0.1:8000/health

# rqinfo (воркер/очередь)
.\.venv\Scripts\rqinfo.exe
```

## 6. Если нужно вспомнить логику обработки

- Архитектура и пайплайн: `docs/AGENT_HANDOFF.md`
- Команды бота и сценарии: `docs/BOT_COMMAND_MATRIX.md`
- Диагностика по коду заявки: `scripts/diagnose_request.py` + `docs/AGENT_HANDOFF.md`
