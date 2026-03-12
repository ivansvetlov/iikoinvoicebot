# Termux SSH Toolkit (tracked)

Этот toolkit лежит в git, значит после `git pull` он доступен на телефоне сразу.

## Быстрый старт (Termux)

```bash
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 192.168.0.135
source ~/.bashrc
whelp
```

## Быстрый старт (Windows)

PowerShell от администратора:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\01_enable_openssh_server_admin.ps1
```

Добавить публичный ключ телефона:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\02_add_termux_pubkey.ps1 -PublicKeyPath .\termux_id_ed25519.pub
```

Показать актуальный IP:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\03_show_connection_info.ps1
```

## Команды toolkit

- Подключение: `wssh`, `wcmd`, `wsetip`, `wfixssh`
- Git: `wstatus`, `wpull`
- Сервисы: `wstart`, `wstop`, `wrestart`, `wps`
- Логи/диагностика: `wtail`, `wlogs`, `wdiag`, `wsmoke`, `wmetrics`, `wdevstatus`
- Сценарии: `wrun monitor|incident|recover|release`
- Агентные команды: `wvibe` (автопрогрев контекста), `wvibe reconnect`, `wreconnect`, `wvibe mcp "<команда>"`, `wmcp "<команда>"`, `waider`

## Перенос в другой проект

Пошаговый перенос описан в:
- `docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md`

Минимально нужно перенести:
- `scripts/termux_ssh_toolkit/`
- `.vibe/agents/phone-wrapper.toml`
- `VIBE.md`

## Если видишь кракозябры

Toolkit уже включает UTF-8 prelude для удаленных PowerShell-команд.

Если локальная Windows-консоль всё равно ломает русский:
```powershell
chcp 65001
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
```
