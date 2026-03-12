# Termux + SSH + Vibe Wrapper Playbook

Этот документ описывает, как перенести текущий подход (работа с телефона через Termux, SSH в Windows и `wvibe` wrapper) в другой проект.

## Что переносить в новый проект

Скопируй в новый репозиторий:
- `scripts/termux_ssh_toolkit/`
- `.vibe/agents/phone-wrapper.toml`
- `VIBE.md`

Это минимальный набор для:
- one-shot установки toolkit на телефоне;
- стабильной SSH-работы;
- wrapper-режима `wvibe` с проектными правилами.

## Минимальные требования

- Windows-машина с OpenSSH Server.
- Телефон с Termux (`git`, `openssh`).
- В проекте на Windows есть Python-окружение (`.venv`) и git-репозиторий.
- Установлен `mistral-vibe` (через `uv tool install mistral-vibe`).

## Быстрая установка в новом проекте

### 1) На Windows
PowerShell от администратора:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\01_enable_openssh_server_admin.ps1
```

Добавить pubkey телефона:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\02_add_termux_pubkey.ps1 -PublicKeyPath .\termux_id_ed25519.pub
```

Проверить IP:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\03_show_connection_info.ps1
```

### 2) На телефоне (Termux)
В корне репозитория:
```bash
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user <WINDOWS_USER> --win-host <WINDOWS_LAN_IP>
source ~/.bashrc
whelp
```

## Что обязательно адаптировать под новый проект

1. Пути по умолчанию (если отличаются):
- `--project "C:\Users\<User>\...\<ProjectDir>"`
- `--uv-bin "C:\Users\<User>\.local\bin"`

2. Сервисный контроллер:
- файл `scripts/termux_ssh_toolkit/windows/05_phone_process_control.ps1`
- обновить блок `$components` под свои entrypoint-команды.

3. Wrapper-политика агента:
- `VIBE.md` — проектные правила, проверки, ограничения.
- `.vibe/agents/phone-wrapper.toml` — профиль агента.

4. Команды проверки:
- `wtest`, `wdevstatus`, `wsmoke`, `wmetrics` в `termux/02_add_aliases.sh` при необходимости подстрой под свои скрипты.

## Как использовать после установки

- Базово:
  - `wssh`
  - `wstatus`
  - `wdiag`
- Агент:
  - `wvibe`
  - `wvibe reconnect` (после обрыва продолжает последнюю сессию)
  - `wreconnect` (короткий алиас)
  - `wvibe "проверь ветку, запусти тесты, дай отчет"`

## Кодировка (fix для кракозябр)

Симптом: в ответах видишь строки вида `РџСЂРёРІРµС‚` вместо русского текста.

Что уже сделано в toolkit:
- В `_wps` добавлен UTF-8 prelude перед каждым удаленным PowerShell-вызовом:
  - `chcp 65001`
  - установка `InputEncoding/OutputEncoding` в UTF-8.

Если проблема всё же повторяется на локальной Windows-консоли:
```powershell
chcp 65001
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
```

И проверь, что файлы сохранены в UTF-8.

## Траблшутинг

- `No such file` в Termux:
  - ты не в каталоге репозитория на телефоне или не сделал `git pull`.
- `command not found: whelp`:
  - `source ~/.bashrc`
- SSH timeout:
  - `wsetip <new_ip>`
  - `wfixssh`
  - `wssh`

## Рекомендация для масштабирования

Для каждого нового проекта держи такой же набор:
- `scripts/termux_ssh_toolkit/`
- `.vibe/agents/`
- `VIBE.md`

Тогда перенос занимает 5-10 минут и не зависит от ручной настройки каждого раза.
