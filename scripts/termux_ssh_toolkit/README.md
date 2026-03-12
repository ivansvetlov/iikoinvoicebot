# Termux SSH Toolkit (tracked)

Этот набор скриптов находится в git и доступен после `git pull`.

## Быстрый старт (телефон / Termux)

1. Открой репозиторий на телефоне.
2. Выполни:

```bash
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 192.168.0.135
source ~/.bashrc
whelp
```

## Быстрый старт (Windows)

1. В PowerShell от администратора:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\01_enable_openssh_server_admin.ps1
```

2. Добавь публичный ключ телефона:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\02_add_termux_pubkey.ps1 -PublicKeyPath .\termux_id_ed25519.pub
```

3. Покажи актуальный IP:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\03_show_connection_info.ps1
```

## Что даёт toolkit

- Подключение: `wssh`, `wcmd`, `wsetip`, `wfixssh`
- Git: `wstatus`, `wpull`
- Сервисы: `wstart`, `wstop`, `wrestart`, `wps`
- Логи/диагностика: `wtail`, `wlogs`, `wdiag`, `wsmoke`, `wmetrics`, `wdevstatus`
- Сценарии: `wrun monitor|incident|recover|release`
- Агентные команды: `wvibe`, `waider`

