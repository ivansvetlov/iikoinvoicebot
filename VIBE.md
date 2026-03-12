# Vibe Wrapper Rules (Project: iikoinvoicebot)

Ты работаешь в репозитории на Windows. Действуй как практичный инженер: доводи задачу до рабочего результата.

## Режим работы
- Сначала быстро собери контекст по коду и состоянию git.
- Затем предложи короткий план (1-4 шага) и сразу выполняй.
- После изменений обязательно проверь результат (тест, smoke, status).
- Отчёт в конце: что изменено, что проверено, где риск.

## Приоритетные команды в этом проекте
- Git-статус:
  - `git status -sb`
  - `git branch --show-current`
- Тесты:
  - `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Dev status:
  - `.\\.venv\\Scripts\\python.exe scripts\\dev_status.py`
- Метрики (60 мин):
  - `.\\.venv\\Scripts\\python.exe scripts\\metrics_report.py --minutes 60`
- Smoke API:
  - `Invoke-RestMethod http://127.0.0.1:8000/health`
  - `Invoke-RestMethod "http://127.0.0.1:8000/metrics/summary?window_minutes=60"`
- Управление сервисами:
  - `powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\termux_ssh_toolkit\\windows\\05_phone_process_control.ps1 -Action status -Target all -ProjectPath "<path>"`
  - `... -Action restart -Target all ...`

## Ограничения
- Не используй разрушительные git-команды (`reset --hard`, `checkout --`, массовые удаления) без явного запроса.
- Не трогай несвязанные файлы.
- Если видишь конфликт с текущими локальными изменениями, остановись и запроси решение.
- Если пользователь просит выполнить точную терминальную команду, используй MCP-инструмент `termux_bridge_run_command` и возвращай фактический вывод.
