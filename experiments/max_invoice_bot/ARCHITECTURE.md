# MAX Invoice Bot — Architecture

Параллельный трек к `app/bot/manager.py` (Telegram). Шаблон: `experiments/grok_max_bridge/`.

## Модули

| Модуль | Роль |
|--------|------|
| `bot.py` | Handlers, state machine, callbacks |
| `task_watcher.py` | Poll `get_task(request_id)` → ответ пользователю |
| `attachments.py` | Скачивание file/image по URL из вложения |
| `keyboards.py` | `invoice_keyboards` dict → maxapi inline |
| `messaging.py` | send/edit/split (4000 chars) |
| `user_ids.py` | Префикс `max:` для user_store / tasks |
| `config.py` | `MAX_INVOICE_BOT_*` |

## Переиспользование (import)

- `app/bot/backend_client`, `invoice_keyboards`, `invoice_posting`, `messages`, `file_storage`
- `app/services/user_store`, `app/task_store`, `app/config`, pipeline через API

## MAX API (dev.max.ru)

- Long polling `GET /updates` (dev)
- `message_created`, `message_callback`, `bot_started`
- Inline keyboard `callback` → payload (те же `inv:`, `mode:`, …)
- Вложения: `file` (PDF/DOCX), `image` (фото)
- Текст ≤ 4000 → `messaging.split_text`

## Worker path

```
MAX bot → POST /process (без chat_id) → RQ worker → task_store.mark_done
MAX bot ← task_watcher poll ← get_task
```

`app/tasks.py` **не меняется** — блок `if chat_id:` не выполняется.

## Ограничения / проверить на токене

- Альбомы (несколько фото одним событием)
- Pin status в личке
- Длина callback payload
