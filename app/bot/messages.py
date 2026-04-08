"""Single place for bot user-facing texts."""

from __future__ import annotations


class Msg:
    STATUS_TITLE = "Статус ваших заявок:"
    STATUS_SCOPE = "Показываю активные заявки за последние {hours} ч."
    STATUS_QUEUE = "В очереди: {queued}"
    STATUS_PROCESSING = "В обработке: {processing}"
    STATUS_REAPED = "Зависшие заявки: {count} (пометил как ошибка по таймауту)."
    STATUS_STALE = "Требуют внимания: {stale}"
    STATUS_STALE_HINT = "Есть зависшие заявки. Отправьте файл повторно."
    STATUS_PENDING = "В черновике файлов: {count}"
    STATUS_LAST_REQUEST = "Последняя заявка: {code}"
    STATUS_LAST_STATE = "Состояние: {status}"
    STATUS_LAST_MESSAGE = "Комментарий: {message}"
    STATUS_EMPTY = "Пока нет заявок в истории."
    STATUS_RETRY_SENT = "Повторно отправил документ в обработку."
    STATUS_RETRY_SOURCE_MISSING = "Не нашел исходный файл для повтора."
    STATUS_RETRY_FAILED = "Не удалось отправить документ повторно. Попробуйте позже."
    STATUS_RETRY_DENIED = "Эта заявка не принадлежит текущему пользователю."
    STATUS_STATE_MAP = {
        "queued": "в очереди",
        "processing": "обрабатывается",
        "ok": "готово",
        "error": "ошибка",
    }
    CMD_STATUS_DESC = "Статус заявок"
    BTN_STATUS_REFRESH = "Обновить статус"
    BTN_STATUS_RETRY = "Повторить обработку"
    CMD_START_DESC = "Перезапуск и авторизация"
    MERGE_ALIASES = {"merge", "объединить", "с"}

    AUTH_ALREADY = (
        "Вы уже авторизованы в iiko.\n\n"
        "Можете отправлять первичную документацию."
    )
    AUTH_START = (
        "Для работы с iiko нужна авторизация.\n"
        "Введите логин iiko:"
    )
    AUTH_NEED_START = (
        "Если нужна авторизация — используйте /start."
    )
    AUTH_PASSWORD = "Теперь введите пароль iiko:"
    AUTH_LOGIN_MISSING = "Логин не найден.\nВведите логин iiko:"
    AUTH_SAVED = (
        "Данные сохранены.\n"
        "Теперь можно отправлять первичную документацию"
    )
    ACCEPTS_FILES = (
        "Я принимаю фото, PDF или DOCX: накладные, УПД, счёт-фактуры, чеки и иные первичные документы.\n"
        "Если нужна авторизация — используйте /start."
    )
    ACCEPTS_ONLY_SUPPORTED = (
        "Я принимаю только фото, PDF или DOCX: накладные, УПД, счёт-фактуры, чеки и иные первичные документы.\n"
        "Отправьте файл.\n"
        "Я верну статус обработки."
    )
    NO_IIKO_CREDENTIALS = (
        "Нет данных для входа в iiko.\n"
        "Нажмите /start и пройдите авторизацию."
    )
    SPLIT_DISABLED = "Режим объединения сейчас отключен."
    SPLIT_ENABLED = (
        "Режим объединения включен.\n"
        "Отправляйте части накладной."
    )
    SPLIT_NOT_ENABLED = (
        "Режим объединения не включен.\n"
        "Введите /split для начала."
    )
    SPLIT_FINISHING = "Завершаю режим объединения."
    SPLIT_CANCELLED = (
        "Режим объединения отменен.\n"
        "Буфер очищен."
    )
    RATE_LIMIT = (
        "Сейчас слишком много файлов.\n"
        "Я продолжу обработку через минуту.\n"
        "Если нужно срочно — отправьте позже."
    )
    FILE_TOO_LARGE = "Фото слишком большое (лимит {max_mb} MB).\nСожмите фото и отправьте снова."
    NO_PENDING = "Нет ожидающих файлов."
    BACKEND_FILES_ERROR = "Ошибка при обработке файлов."
    BACKEND_FILE_ERROR = "Ошибка при обработке файла."
    BACKEND_SEND_FILES_FAILED = (
        "Не удалось отправить файлы на обработку.\n"
        "Проверьте соединение и попробуйте снова."
    )
    BACKEND_SEND_FILE_FAILED = (
        "Не удалось отправить файл на обработку.\n"
        "Проверьте соединение и попробуйте снова."
    )
    BATCH_COLLECTED = "Собрано файлов: {count}.\nОтправляю на сервер…"
    FILE_RECEIVED_SENDING = "Файл получен.\nОтправляю на сервер…"
    FILE_ON_SERVER_PROCESSING = "Файл на сервере.\nИдет обработка…"
    PROCESSING_SEPARATELY = "Обрабатываю {count} файлов отдельно…"
    FILE_PROGRESS = "Файл {index}/{total}.\nОтправляю на сервер…"
    FILE_DONE = "Файл {index}/{total} обработан.\n{result}"
    MEDIA_GROUP_BATCH = "Получено файлов в одном сообщении: {count}.\nОбрабатываю объединением…"

    PENDING_SINGLE = (
        "📄 Файл добавлен.\n"
        "Можно отправить ещё фото.\n"
        "\n"
        "ВАЖНО: когда будете готовы, нажмите\n «▶️ Отправить в обработку».\n"
    )
    PENDING_MULTI = (
        "Собрано файлов: {count}.\n"
        "Можете продолжить отправку документов.\n"
        "\n"
        "Нажмите\n«🟩 Объединить и отправить», когда будете готовы.\n"
    )
    PENDING_DUPS = (
        "\nНайдено дубликатов: {count}.\n"
        "\n"
        "Можно удалить дубликаты кнопкой ниже."
    )
    PENDING_WAIT = (
        "Черновик сохранён.\n"
        "Отправляйте ещё файлы.\n"
        "\n"
        "Когда будете готовы, нажмите «🟩 Объединить и отправить»."
    )
    NO_PENDING_REUPLOAD = (
        "Нет ожидающих файлов.\n"
        "Отправьте файлы заново."
    )
    MODE_UNKNOWN = "Неизвестный выбор.\nИспользуйте кнопки."
    SENDING_PROCESS = "⏳ Отправляю на обработку…"
    MERGING_SENDING = "⏳ Объединяю и отправляю на обработку…"
    DEDUP_DONE = "Готово.\nУдалено дубликатов: {removed}.\nФайлов в черновике: {kept}."

    EDIT_CANCELLED = "Редактирование отменено."
    EDIT_NO_ACTIVE = "Нет активного редактирования."
    EDIT_WHAT = "Что редактируем?"
    EDIT_SELECT_FIELD = "Выберите поле для изменения:"
    EDIT_SELECT_ITEM = "Выберите товар для изменения:"
    EDIT_SELECT_ITEM_FIELD = "Выберите поле товара:"
    EDIT_ENTER_FIELD = "Введите значение для поля: {field}"
    EDIT_ENTER_ITEM_FIELD = "Введите новое значение для поля: {field}"
    EDIT_NOT_FOUND_REQUEST = "Не нашёл данные по заявке."
    ACTION_CANCELLED = "Отменено."
    BAD_COMMAND = "Некорректная команда"

    IIKO_SOURCE_MISSING = "Не нашёл исходные файлы для отправки.{code_line}"
    IIKO_FILE_NOT_FOUND = "Файл не найден для отправки.{code_line}"
    IIKO_FAILED = "Не удалось отправить в iiko.{code_line}"
    IIKO_OK = "✅ Успешно отправлено в iiko.{code_line}"

    PDF_MODE = (
        "Выберите режим обработки этого PDF.\n"
        "Текущий режим по умолчанию: {current}.\n"
        "\n"
        "Если документ нечеткий, выбирайте accurate."
    )
    PDF_SET_FAST = "Режим PDF установлен: fast."
    PDF_SET_ACCURATE = "Режим PDF установлен: accurate."
    NO_PENDING_FILE_REUPLOAD = "Нет ожидающих файлов.\nОтправьте файл заново."

    SPLIT_WAIT = (
        "Ок.\n"
        "Отправляйте ещё файлы в этот же черновик.\n"
        "\n"
        "Когда закончите, нажмите «✅ Завершить»."
    )
    SPLIT_CANCEL_INFO = (
        "Черновик объединения очищен.\n"
        "Можно сразу отправлять новые файлы как обычно."
    )
    SPLIT_NOT_ENABLED_SHORT = "Режим объединения не включен.\nВведите /split."
    SPLIT_EMPTY = "Пока нет файлов.\nОтправьте части."
    SPLIT_SENDING = "⏳ Отправляю на сервер…"
    SPLIT_PROMPT = (
        "Собрано файлов: {count}.\n"
        "Можно добавить ещё файлы.\n"
        "\n"
        "ВАЖНО: нажмите «✅ Завершить», когда всё готово.\n"
    )
    SPLIT_DUPS = (
        "\nНайдено дубликатов: {count}.\n"
        "\n"
        "Можно удалить дубликаты кнопкой ниже."
    )

    SOFT_DUP_ONE = (
        "Похоже, среди отправленных фото/файлов есть дубликат.\n"
        "Я не блокирую его и оставляю в черновике."
    )
    SOFT_DUP_MANY = (
        "Похоже, среди отправленных фото/файлов есть дубликаты ({count}).\n"
        "Я не блокирую их и оставляю в черновике."
    )

    BTN_FAST = "⚡ fast"
    BTN_ACCURATE = "🎯 accurate"
    BTN_PROCESS_NOW = "▶️ Обработать сейчас"
    BTN_MERGE_SEND = "🟩 Объединить и отправить"
    BTN_DEDUP = "🧹 Удалить дубликаты"
    BTN_EDIT_INFO = "🧾 Редактировать информацию"
    BTN_EDIT_ITEMS = "📦 Редактировать товары"
    BTN_DONE = "✅ Готово"
    BTN_CANCEL = "✖ Отмена"
    BTN_BACK = "◀ Назад"
    BTN_ITEM_ROW = "{index}. {title}"
    ITEM_FALLBACK = "Позиция {idx}"
    BTN_ITEM_NAME = "Название"
    BTN_ITEM_QTY = "Кол-во"
    BTN_ITEM_PRICE = "Цена"
    BTN_ITEM_TOTAL = "Сумма с НДС"
    BTN_ITEM_VAT = "НДС"
    BTN_INV_EDIT = "✏ Редактировать"
    BTN_INV_SEND = "✅ Отправить в iiko"
    BTN_SPLIT_CANCEL = "✖ Отменить"
    BTN_SPLIT_DONE = "✅ Завершить"

    INFO_FIELDS = {
        "supplier": "Поставщик",
        "consignee": "Грузополучатель",
        "delivery_address": "Адрес доставки",
        "invoice_date": "Дата",
        "invoice_number": "Номер",
    }
    ITEM_FIELDS = {
        "name": "Название",
        "unit_amount": "Кол-во",
        "unit_price": "Цена",
        "cost_with_tax": "Сумма с НДС",
        "tax_amount": "НДС",
    }

    RESP_QUEUED_DEFAULT = "Принято.\nОжидайте результат."
    RESP_OK = "Готово."
    RESP_ERROR = "Не получилось обработать файл."
    RESP_ERROR_BATCH = "Не получилось обработать файлы."
    RESP_STATUS = "Статус: {status}"
    RESP_ITEMS_RECOGNIZED = "Распознано позиций: {count}"
    RESP_IIKO_UPLOADED = "iiko: загружено."
    RESP_WARNINGS = "Предупреждения: {warnings}"
    RESP_CODE = "Код заявки: {code}"
    CODE_LINE = "\n\nКод заявки: {code}"

    RESP_HINTS = {
        "unsupported_format": "Поддерживаемые форматы:\nфото (JPG/PNG), PDF, DOCX.",
        "bad_pdf": "PDF повреждён.\nПопробуйте пересохранить файл и отправить снова.",
        "bad_docx": "DOCX повреждён.\nПопробуйте пересохранить файл и отправить снова.",
        "empty_file": "Похоже, файл пустой.\nПроверьте и отправьте снова.",
        "file_too_large": "Сожмите файл.\nМаксимум {max_upload_mb} MB.",
        "not_invoice": (
            "Проверьте, что файл относится к первичной документации.\n"
            "Проверьте, что позиции различимы."
        ),
        "llm_timeout": "Распознавание отвечает медленно.\nПопробуйте через минуту.",
        "llm_unavailable": "Распознавание временно недоступно.\nПопробуйте позже.",
        "llm_bad_response": (
            "Распознавание вернуло неполный или некорректный ответ.\n\n"
            "Попробуйте отправить цельный PDF или одно фото накладной."
        ),
        "llm_garbage": (
            "Распознавание «зациклилось» (много повторов или нулей).\n"
            "Попробуйте одно ровное фото или PDF с цельной таблицей."
        ),
        "iiko_auth_missing": "Нажмите /start и введите логин/пароль iiko.",
        "iiko_upload_failed": "Не удалось загрузить в iiko.\nПопробуйте позже.",
    }

    NOT_INVOICE_MESSAGE = (
        "Похоже, файл не содержит целевых данных или позиции не читаются.\n\n"
        "Проверьте, что в документе различима таблица позиций.\n\n"
    )
    BATCH_NOT_INVOICE_MESSAGE = (
        "Похоже, файлы не содержат целевых данных или позиции не читаются.\n\n"
        "Проверьте, что в документах различимы таблицы позиций.\n\n"
    )
    PHOTO_SPLIT_HINT = "Если фото разрезано на части — попробуйте /split и отправьте части отдельно."

    INVOICE_UNKNOWN = "—"
    INVOICE_TITLE = "📄 Документ распознан"
    INVOICE_SUPPLIER = "📦 Поставщик: {supplier}"
    INVOICE_CONSIGNEE = "🏢 Грузополучатель: {consignee}"
    INVOICE_DELIVERY = "📍 Адрес доставки: {delivery}"
    INVOICE_DATE = "📅 Дата: {date}"
    INVOICE_NUMBER = "📋 Номер накладной: {number}"
    INVOICE_ITEMS = "Товары:"
    INVOICE_ITEM_LINE = "{index}. {name}"
    INVOICE_ITEM_QTY = "- Кол-во: {qty}"
    INVOICE_ITEM_PRICE = "- Цена: {price} ₽"
    INVOICE_ITEM_TOTAL = "- Сумма с НДС: {total} ₽ (НДС: {vat} ₽)"
    INVOICE_SEPARATOR = "──────────"
    INVOICE_VAT_SUM = "📊 Сумма НДС: {vat} ₽"
    INVOICE_TOTAL_SUM = "💰 ИТОГО с НДС: {total} ₽"
