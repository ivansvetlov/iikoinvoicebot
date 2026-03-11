# Каталог пользовательских сообщений

Документ с текстами сообщений, которые отправляются пользователю.
Если хотите править формулировки, ориентируйтесь на `source:line` в таблице ниже.

## Источники
- `app/bot/manager.py`
- `app/tasks.py`
- `app/api.py`
- `app/services/pipeline.py`
- `app/utils/user_messages.py`

## Сообщения

| Source | Kind | Text |
| --- | --- | --- |
| `app/api.py:191` | `response:message` | Файл принят в очередь. Результат пришлем позже. |
| `app/api.py:306` | `response:message` | Файлы приняты в очередь. Результат пришлем позже. |
| `app/bot/manager.py:127` | `call:answer` | Вы уже авторизованы в iiko. Можете отправлять накладные. |
| `app/bot/manager.py:129` | `call:answer` | Для работы с iiko нужна авторизация. Введите логин iiko: |
| `app/bot/manager.py:159` | `call:answer` | Режим обработки PDF: Сейчас: {...} fast — быстрее, для четких файлов. accurate — точнее, для сложных случаев |
| `app/bot/manager.py:171` | `call:answer` | Неверный режим. Используйте `/mode fast` или `/mode accurate`. |
| `app/bot/manager.py:176` | `call:answer` | Готово. Режим PDF: {...}. |
| `app/bot/manager.py:184` | `call:answer` | Готово. Режим PDF: fast. |
| `app/bot/manager.py:192` | `call:answer` | Готово. Режим PDF: accurate. |
| `app/bot/manager.py:212` | `call:answer` | Я принимаю фото, PDF или DOCX накладной. Если нужна авторизация — используйте /start. |
| `app/bot/manager.py:224` | `call:answer` | Теперь введите пароль iiko: |
| `app/bot/manager.py:232` | `call:answer` | Логин не найден. Введите логин iiko: |
| `app/bot/manager.py:237` | `call:answer` | Данные сохранены. Теперь можно отправлять накладные. |
| `app/bot/manager.py:241` | `call:answer` | Я принимаю фото, PDF или DOCX накладной. Если нужна авторизация — используйте /start. |
| `app/bot/manager.py:250` | `call:answer` | Режим объединения сейчас отключен. |
| `app/bot/manager.py:254` | `call:answer` | Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию. |
| `app/bot/manager.py:265` | `call:answer` | Режим объединения включен. Отправляйте части накладной. |
| `app/bot/manager.py:276` | `call:answer` | Режим объединения не включен. Введите /split для начала. |
| `app/bot/manager.py:278` | `call:answer` | Завершаю режим объединения. |
| `app/bot/manager.py:290` | `call:answer` | Режим объединения отменен. Буфер очищен. |
| `app/bot/manager.py:299` | `call:answer` | Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию. |
| `app/bot/manager.py:304` | `call:answer` | Сейчас слишком много файлов. Я продолжу обработку через минуту. Если нужно срочно — отправьте позже.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:339` | `call:answer` | Нет данных для входа в iiko. Нажмите /start и пройдите авторизацию. |
| `app/bot/manager.py:346` | `call:answer` | Фото слишком большое (лимит {...} MB). Сожмите фото и отправьте снова. |
| `app/bot/manager.py:353` | `call:answer` | Сейчас слишком много файлов. Я продолжу обработку через минуту. Если нужно срочно — отправьте позже.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:449` | `call:answer` | Я принимаю только фото, PDF или DOCX накладной. Отправьте файл, и я верну статус обработки. |
| `app/bot/manager.py:485` | `call:answer` | Нет ожидающих файлов. |
| `app/bot/manager.py:513` | `call:send_message` | Нет ожидающих файлов. |
| `app/bot/manager.py:528` | `call:edit_text` | Файл получен. Отправляю на сервер… |
| `app/bot/manager.py:536` | `call:send_message` | Файл получен. Отправляю на сервер… |
| `app/bot/manager.py:538` | `call:edit_text` | Файл на сервере. Идет обработка… |
| `app/bot/manager.py:550` | `call:edit_text` | Ошибка при обработке файла. |
| `app/bot/manager.py:553` | `call:send_message` | Не удалось отправить файл на обработку. Проверьте соединение и попробуйте снова.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:565` | `call:send_message` | Обрабатываю {...} файлов отдельно… |
| `app/bot/manager.py:568` | `call:edit_text` | Файл {...}/{...}. Отправляю на сервер… |
| `app/bot/manager.py:572` | `call:edit_text` | Файл {...}/{...} обработан. {...} |
| `app/bot/manager.py:579` | `call:send_message` | Не удалось отправить файл на обработку. Проверьте соединение и попробуйте снова.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:596` | `call:answer` | Нет ожидающих файлов. |
| `app/bot/manager.py:649` | `call:send_message` | Получено файлов в одном сообщении: {...}. Обрабатываю объединением… |
| `app/bot/manager.py:662` | `call:edit_text` | Ошибка при обработке файлов. |
| `app/bot/manager.py:665` | `call:send_message` | Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:733` | `call:edit_text` | Ок, жду ещё файлы. Отправляйте. |
| `app/bot/manager.py:738` | `call:answer` | Нет ожидающих файлов. Отправьте файлы заново.\nКод события: {EVENT_CODE} |
| `app/bot/manager.py:753` | `call:edit_text` | ⏳ Отправляю на обработку… |
| `app/bot/manager.py:771` | `call:answer` | Неизвестный выбор. Используйте кнопки. |
| `app/bot/manager.py:779` | `call:answer` | Некорректная команда |
| `app/bot/manager.py:785` | `call:edit_text` | Отменено. |
| `app/bot/manager.py:792` | `call:answer` | Не нашёл данные по заявке. |
| `app/bot/manager.py:809` | `call:answer` | Нет активного редактирования. |
| `app/bot/manager.py:832` | `call:edit_text` | Редактирование отменено. |
| `app/bot/manager.py:839` | `call:edit_text` | Введите значение для поля: {...} |
| `app/bot/manager.py:854` | `call:edit_text` | Введите новое значение для поля: {...} |
| `app/bot/manager.py:896` | `call:_reply` | Что редактируем? |
| `app/bot/manager.py:918` | `call:_reply` | Выберите поле для изменения: |
| `app/bot/manager.py:932` | `call:_reply` | Выберите товар для изменения: |
| `app/bot/manager.py:954` | `call:_reply` | Выберите поле товара: |
| `app/bot/manager.py:998` | `call:edit_text` | Не нашёл исходные файлы для отправки. |
| `app/bot/manager.py:1023` | `call:edit_text` | Файл не найден для отправки. |
| `app/bot/manager.py:1036` | `call:edit_text` | Не удалось отправить в iiko. |
| `app/bot/manager.py:1040` | `call:edit_text` | ✅ Успешно отправлено в iiko. |
| `app/bot/manager.py:1042` | `call:edit_text` | Не удалось отправить в iiko. |
| `app/bot/manager.py:1075` | `call:answer` | Нет ожидающих файлов. Отправьте файл заново. |
| `app/bot/manager.py:1080` | `call:edit_text` | Режим PDF установлен: fast. |
| `app/bot/manager.py:1089` | `call:edit_text` | Режим PDF установлен: accurate. |
| `app/bot/manager.py:1111` | `call:edit_text` | Режим объединения не включен. Введите /split. |
| `app/bot/manager.py:1123` | `call:edit_text` | Режим объединения отменен. Буфер очищен. |
| `app/bot/manager.py:1137` | `call:answer` | Неизвестный выбор. Используйте кнопки. |
| `app/bot/manager.py:1163` | `call:edit_text` | Пока нет файлов. Отправьте части. |
| `app/bot/manager.py:1177` | `call:edit_text` | ⏳ Отправляю на сервер… |
| `app/bot/manager.py:1193` | `call:send_message` | Собрано файлов: {...}. Отправляю на сервер… |
| `app/bot/manager.py:1207` | `call:edit_text` | Ошибка при обработке файлов. |
| `app/bot/manager.py:1210` | `call:send_message` | Не удалось отправить файлы на обработку. Проверьте соединение и попробуйте снова.\nКод события: {EVENT_CODE} |
| `app/services/pipeline.py:1424` | `response:message` | Сервис распознавания временно не отвечает. Попробуйте отправить файл чуть позже. |
| `app/services/pipeline.py:1436` | `response:message` | Сервис распознавания временно недоступен. Попробуйте позже. |
| `app/services/pipeline.py:1448` | `response:message` | Не удалось обработать файл на сервере. Попробуйте ещё раз или отправьте файл в другом формате. |
| `app/services/pipeline.py:1516` | `response:message` | Файл обработан. Позиции извлечены. |
| `app/services/pipeline.py:1527` | `response:message` | Нет данных для входа в iiko. Нажмите /start и введите логин/пароль. |
| `app/services/pipeline.py:1541` | `response:message` | Позиции загружены в iiko. |
| `app/services/pipeline.py:1558` | `response:message` | Не удалось загрузить позиции в iiko. Попробуйте позже. |
| `app/services/pipeline.py:1605` | `response:message` | Не удалось обработать файлы. Проверьте формат и попробуйте снова. |
| `app/services/pipeline.py:1649` | `response:message` | Похоже, это не накладная. Отправьте корректный документ. |
| `app/services/pipeline.py:1659` | `response:message` | Файлы обработаны. Позиции объединены. |
| `app/services/pipeline.py:1670` | `response:message` | Нет данных для входа в iiko. Нажмите /start и введите логин/пароль. |
| `app/services/pipeline.py:1683` | `response:message` | Позиции загружены в iiko. |
| `app/services/pipeline.py:1700` | `response:message` | Не удалось загрузить позиции в iiko. Попробуйте позже. |
| `app/utils/user_messages.py:69` | `formatter:format_user_response` | Принято. Результат пришлю позже. |
| `app/utils/user_messages.py:71` | `formatter:format_user_response` | Готово. |
| `app/utils/user_messages.py:73` | `formatter:format_user_response` | Не получилось обработать файл. |
| `app/utils/user_messages.py:75` | `formatter:format_user_response` | Статус: |
| `app/utils/user_messages.py:86` | `formatter:format_user_response` | Распознано позиций: |
| `app/utils/user_messages.py:89` | `formatter:format_user_response` | iiko: загружено. |
| `app/utils/user_messages.py:94` | `formatter:format_user_response` | Предупреждения: |
| `app/utils/user_messages.py:100` | `formatter:format_user_response` | Поддерживаемые форматы: фото (JPG/PNG), PDF, DOCX. |
| `app/utils/user_messages.py:101` | `formatter:format_user_response` | PDF повреждён. Попробуйте пересохранить файл и отправить снова. |
| `app/utils/user_messages.py:102` | `formatter:format_user_response` | DOCX повреждён. Попробуйте пересохранить файл и отправить снова. |
| `app/utils/user_messages.py:103` | `formatter:format_user_response` | Похоже, файл пустой. Проверьте и отправьте снова. |
| `app/utils/user_messages.py:104` | `formatter:format_user_response` | Сожмите файл. Максимум |
| `app/utils/user_messages.py:106` | `formatter:format_user_response` | Проверьте, что это накладная, УПД или ТОРГ‑12, и что видно таблицу с позициями (строки и колонки). |
| `app/utils/user_messages.py:109` | `formatter:format_user_response` | Распознавание отвечает медленно. Попробуйте через минуту. |
| `app/utils/user_messages.py:110` | `formatter:format_user_response` | Распознавание временно недоступно. Попробуйте позже. |
| `app/utils/user_messages.py:112` | `formatter:format_user_response` | Распознавание вернуло неполный или некорректный ответ. Попробуйте отправить цельный PDF или одно фото накладной. |
| `app/utils/user_messages.py:116` | `formatter:format_user_response` | Распознавание «зациклилось» (много повторов или нулей). Попробуйте одно ровное фото или PDF с цельной таблицей. |
| `app/utils/user_messages.py:119` | `formatter:format_user_response` | Нажмите /start и введите логин/пароль iiko. |
| `app/utils/user_messages.py:120` | `formatter:format_user_response` | Не удалось загрузить в iiko. Попробуйте позже. |
| `app/utils/user_messages.py:130` | `formatter:format_user_response` | Код заявки: |
| `app/utils/user_messages.py:153` | `formatter:format_invoice_markdown` | 📄 Распознанная накладная |
| `app/utils/user_messages.py:155` | `formatter:format_invoice_markdown` | 📦 Поставщик: |
| `app/utils/user_messages.py:156` | `formatter:format_invoice_markdown` | 🏢 Грузополучатель: |
| `app/utils/user_messages.py:157` | `formatter:format_invoice_markdown` | 📍 Адрес доставки: |
| `app/utils/user_messages.py:158` | `formatter:format_invoice_markdown` | 📅 Дата: |
| `app/utils/user_messages.py:159` | `formatter:format_invoice_markdown` | 📋 Номер накладной: |
| `app/utils/user_messages.py:161` | `formatter:format_invoice_markdown` | Товары: |
| `app/utils/user_messages.py:187` | `formatter:format_invoice_markdown` | - Кол-во: |
| `app/utils/user_messages.py:188` | `formatter:format_invoice_markdown` | - Масса: |
| `app/utils/user_messages.py:189` | `formatter:format_invoice_markdown` | - Цена: |
| `app/utils/user_messages.py:190` | `formatter:format_invoice_markdown` | - Сумма без НДС: |
| `app/utils/user_messages.py:191` | `formatter:format_invoice_markdown` | - НДС: |
| `app/utils/user_messages.py:192` | `formatter:format_invoice_markdown` | - Сумма с НДС: |
| `app/utils/user_messages.py:196` | `formatter:format_invoice_markdown` | 📊 Сумма НДС: |
| `app/utils/user_messages.py:197` | `formatter:format_invoice_markdown` | 💰 ИТОГО с НДС: |
| `app/utils/user_messages.py:202` | `formatter:format_invoice_markdown` | Код заявки: |

## Обновление каталога
```powershell
.\.venv\Scripts\python.exe scripts\export_user_messages.py
```
