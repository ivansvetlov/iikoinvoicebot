# Папка `app/bot/`

Здесь лежит логика Telegram-бота.

Основной файл:
- `manager.py` — класс `TelegramBotManager`, который:
  - регистрирует хендлеры (`/start`, `/mode`, `/split`, `/done`, `/cancel`, `/multi` и др.);
  - обрабатывает фото/документы/альбомы и решает, куда их отправлять (split/pending/batch);
  - общается с backend (`/process`, `/process-batch`);
  - форматирует ответы пользователю (через `app.utils.user_messages`).
- `event_codes.py` — единый реестр пользовательских кодов событий (`BOT_*`) и helper для формата `Код события: ...`.

Запуск бота осуществляется из корневого `bot.py`, который создаёт экземпляр `TelegramBotManager`.
