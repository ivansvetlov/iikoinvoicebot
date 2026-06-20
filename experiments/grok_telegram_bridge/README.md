# Grok ↔ Telegram Bridge

Удалённый доступ к **локальному Grok CLI** с телефона — как терминальный `grok -p`, но через отдельного Telegram-бота.

**Не путать с `iikoinvoicebot`** — другой токен, другой процесс, другая ветка (`exp/grok-telegram-bridge`).

## Архитектура

```
Telegram (ты) → Bridge Bot (aiogram) → grok.exe headless → ответ в TG
                      ↓
              sessions.json (sessionId для --resume)
```

| Слой | Файл | Роль |
|------|------|------|
| Telegram UI | `bot.py` | команды, streaming edit, chunking |
| Grok CLI | `grok_runner.py` | `grok -p --output-format streaming-json --resume` |
| Сессии | `session_store.py` | parity с `grok --resume <sessionId>` |
| Метапромпт | `agents/METAPROMPT.md` | авто `--rules` на каждый запрос |
| Тестировщик | `tester.py` + `--check` | встроенный verifier (check-work skill) |
| Доступ | `security.py` | allowlist user_id |

### Что НЕ добавляли (и почему)

| Идея | Вердикт |
|------|---------|
| **MCP** | Не нужен отдельно — Grok CLI уже читает `~/.grok/config.toml` |
| **Cron** | Не нужен — бот long-polling; таймеры для чата избыточны |
| **Отдельный tester subprocess** | Дублирует `--check` в CLI |

## Настройка

### 1. Создай бота в @BotFather

Получи токен → в `.env`:

```env
GROK_BRIDGE_BOT_TOKEN=123456:ABC...
GROK_BRIDGE_ALLOWED_USER_IDS=6106711925
```

Твой `user_id` — у @userinfobot или из логов invoice-бота.

### 2. Опционально

```env
GROK_CLI_PATH=C:\Users\MiBookPro\.grok\bin\grok.exe
GROK_BRIDGE_CWD=C:\Users\MiBookPro\PycharmProjects\PythonProject
GROK_BRIDGE_MODEL=grok-build
GROK_BRIDGE_YOLO=true
GROK_BRIDGE_STREAM=true
GROK_BRIDGE_MAX_TURNS=40
GROK_BRIDGE_TIMEOUT_SEC=900
GROK_BRIDGE_AUTO_CHECK=false
```
Метапромпт (`agents/METAPROMPT.md`) подгружается через `grok --rules`. После правок: `/new`.

### 3. Запуск

```powershell
.\.venv\Scripts\python.exe -m experiments.grok_telegram_bridge
```

ПК должен быть включён, WireGuard/Telegram доступны, Grok авторизован (`grok -p "ping"` работает).

## Команды в Telegram

| Команда | Действие |
|---------|----------|
| `/new` | новая сессия (без `--resume`) |
| `/status` | cwd, session id, yolo |
| `/yolo on\|off` | `--always-approve` (авто-approve tools) |
| `/check …` | запрос + **тестировщик** (`--check`) |
| текст | `grok -p` + `--resume` |

## Тестировщик

Как в терминале: `grok -p "…" --check` → subagent verifier (skill check-work).

См. `agents/tester.md`.

## Требования

- Grok CLI установлен и залогинен
- Тот же `.venv` что у проекта (aiogram)
- **Один** VPN (WireGuard), Telegram API доступен

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_grok_bridge -v
```
