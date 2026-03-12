#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Usage:
#   bash 02_add_aliases.sh [windows_user] [windows_host] [host_alias] [project_win_path] [uv_bin_win_path]
#
# Example:
#   bash 02_add_aliases.sh MiBookPro 192.168.0.135 windev "C:\Users\MiBookPro\PycharmProjects\PythonProject" "C:\Users\MiBookPro\.local\bin"

WIN_USER="${1:-MiBookPro}"
WIN_HOST="${2:-192.168.0.135}"
HOST_ALIAS="${3:-windev}"
WIN_PROJECT="${4:-C:\Users\MiBookPro\PycharmProjects\PythonProject}"
WIN_UV_BIN="${5:-C:\Users\MiBookPro\.local\bin}"

SSH_DIR="$HOME/.ssh"
SSH_CONFIG="$SSH_DIR/config"
BASHRC="$HOME/.bashrc"

SSH_BLOCK_BEGIN="# >>> ${HOST_ALIAS}-ssh-host >>>"
SSH_BLOCK_END="# <<< ${HOST_ALIAS}-ssh-host <<<"
BASH_BLOCK_BEGIN="# >>> ${HOST_ALIAS}-dev-toolkit >>>"
BASH_BLOCK_END="# <<< ${HOST_ALIAS}-dev-toolkit <<<"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
[ -f "$SSH_CONFIG" ] || touch "$SSH_CONFIG"
[ -f "$BASHRC" ] || touch "$BASHRC"

strip_block() {
  local file="$1"
  local begin="$2"
  local end="$3"
  local tmp
  tmp="$(mktemp)"
  awk -v b="$begin" -v e="$end" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

strip_block "$SSH_CONFIG" "$SSH_BLOCK_BEGIN" "$SSH_BLOCK_END"
strip_block "$BASHRC" "$BASH_BLOCK_BEGIN" "$BASH_BLOCK_END"

cat >> "$SSH_CONFIG" <<EOF
$SSH_BLOCK_BEGIN
Host $HOST_ALIAS
  HostName $WIN_HOST
  User $WIN_USER
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  PreferredAuthentications publickey
  PubkeyAuthentication yes
  PasswordAuthentication no
  KbdInteractiveAuthentication no
  ConnectTimeout 5
  ConnectionAttempts 1
  ServerAliveInterval 20
  ServerAliveCountMax 2
  ControlMaster no
$SSH_BLOCK_END
EOF

cat >> "$BASHRC" <<EOF
$BASH_BLOCK_BEGIN
export WINDEV_ALIAS="$HOST_ALIAS"
export WINDEV_USER="$WIN_USER"
export WINDEV_HOST="$WIN_HOST"
export WINDEV_PROJECT_WIN="$WIN_PROJECT"
export WINDEV_UV_BIN="$WIN_UV_BIN"

_wssh_base() {
  ssh \
    -o ControlMaster=no \
    -o ConnectTimeout=5 \
    -o ConnectionAttempts=1 \
    -o PreferredAuthentications=publickey \
    -o PubkeyAuthentication=yes \
    -o IdentitiesOnly=yes \
    "\$@"
}

_wps() {
  local cmd="\$*"
  local prelude="chcp 65001 > \\\$null; [Console]::InputEncoding=[System.Text.UTF8Encoding]::new(\\\$false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\\\$false); \\\$OutputEncoding=[Console]::OutputEncoding"
  _wssh_base "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -Command "\$prelude; \$cmd"
}

_confirm() {
  local prompt="\${1:-Продолжить?}"
  read -r -p "\$prompt [y/N]: " ans
  case "\$ans" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

wsets() {
  cat <<'SETS'
НАБОРЫ КОМАНД (готовые сценарии)

1) Начало дня:
   wps
   wstatus
   wdevstatus

2) Запуск всего стека:
   wstart all
   wps
   wtail backend

3) После правок в коде:
   wtest
   wrestart all
   wsmoke

4) Деплой-проход:
   wdeploy --dry-run
   wdeploy --yes

5) Аварийный режим:
   wrun incident

6) Восстановление:
   wrun recover

7) Релизный прогон:
   wrun release
SETS
}

whelp() {
  local topic="\${1:-all}"
  case "\$topic" in
    sets|set|scenarios|scenario)
      wsets
      return 0
      ;;
  esac

  cat <<'HELP'
ТЕЛЕФОН -> ПК: ПОЛНЫЙ СПРАВОЧНИК

Что это:
  Ты в Termux на телефоне.
  Любая команда w* выполняется на Windows-ПК по SSH.

Быстрый старт (минимум):
  1) wstatus
  2) wtest
  3) wdeploy --yes
  4) wtail worker

СВЯЗЬ И БАЗА:
  whelp
    Полная справка (этот экран).
  whelp sets
    Только готовые наборы команд.
  wfixssh
    Локально чинит SSH-права/сокеты в Termux.
  wsetip <ip_пк>
    Обновить IP в ~/.ssh/config для alias.
  wssh
    Открыть обычную SSH-сессию на ПК.
  wcmd "<PowerShell-команда>"
    Выполнить одну команду на ПК.
    Пример: wcmd "Get-Date"

ПРОЕКТ И GIT:
  wproj
    Показать путь проекта на ПК.
  wstatus
    git status -sb + текущая ветка.
  wpull
    Безопасно обновить ветку: git pull --ff-only.

СЕРВИСЫ (backend/worker/bot):
  wstart [all|backend|worker|bot]
    Запустить сервис(ы).
  wstop [all|backend|worker|bot]
    Остановить сервис(ы).
  wrestart [all|backend|worker|bot]
    Перезапустить сервис(ы).
  wps
    Показать up/down + pid по всем сервисам.

ЛОГИ И ДИАГНОСТИКА:
  wtail [backend|worker|bot|file.log]
    Смотреть live-лог.
    Примеры:
      wtail worker
      wtail backend
      wtail backend.out.log
  wlogs [...]
    То же самое, алиас к wtail.
  wdevstatus
    Проверка dev-окружения.
  wmetrics
    Отчет по метрикам (окно 60 минут).
  wsmoke
    Быстрая проверка: dev_status + /health + /metrics/summary.
  wdiag
    Один экран: host + git + services + smoke.

ТЕСТЫ И ДЕПЛОЙ:
  wtest
    Запуск unittest.
  wdeploy [--dry-run] [--yes]
    Рабочий цикл:
      1) pull
      2) test
      3) restart all
      4) smoke
    --dry-run: только показать план.
    --yes: выполнить без вопроса.

АГЕНТЫ:
  wvibe [текст задачи]
    Запустить Mistral Vibe в режиме project-wrapper.
    Если передан текст, он отправится как стартовая задача.
  waider
    Запустить aider в проекте (если установлен).

ГОТОВЫЕ СЦЕНАРИИ:
  wrun monitor
    Статус + метрики.
  wrun incident
    Полная диагностика + live-лог worker.
  wrun recover
    Перезапуск всего + smoke + status.
  wrun release
    Статус + deploy-цикл.

ЕСЛИ НЕ РАБОТАЕТ:
  1) "command not found: whelp"
     Выполни: source ~/.bashrc
  2) SSH timeout
     Обнови IP: wsetip <новый_ip_пк>
     Проверь порт: ncat <ip_пк> 22
     Потом: ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes <user>@<ip_пк>
  3) Ключ просит пароль
     Запусти: wfixssh

Для сценариев одной командой:
  whelp sets
HELP
}

wh() { whelp "\$@"; }

wfixssh() {
  mkdir -p "\$HOME/.ssh"
  chmod 700 "\$HOME/.ssh"
  [ -f "\$HOME/.ssh/id_ed25519" ] && chmod 600 "\$HOME/.ssh/id_ed25519"
  [ -f "\$HOME/.ssh/id_ed25519.pub" ] && chmod 644 "\$HOME/.ssh/id_ed25519.pub"
  rm -f "\$HOME/.ssh"/cm-* 2>/dev/null || true
  echo "SSH local state fixed."
  echo "Now test: wssh"
}

wsetip() {
  local ip="\${1:-}"
  local cfg="\$HOME/.ssh/config"
  if [ -z "\$ip" ]; then
    echo "Usage: wsetip <new_windows_ip>"
    return 1
  fi
  if [ ! -f "\$cfg" ]; then
    echo "No ~/.ssh/config found"
    return 1
  fi

  if awk -v host="\$WINDEV_ALIAS" -v ip="\$ip" '
      $1=="Host" {
        inhost=($2==host)
        print
        next
      }
      inhost && $1=="HostName" {
        print "  HostName " ip
        changed=1
        next
      }
      { print }
      END { exit(changed ? 0 : 1) }
    ' "\$cfg" > "\$cfg.tmp"; then
    mv "\$cfg.tmp" "\$cfg"
    export WINDEV_HOST="\$ip"
    echo "Updated \$WINDEV_ALIAS -> \$ip"
    echo "Now test: wssh"
  else
    rm -f "\$cfg.tmp"
    echo "Could not update host '\$WINDEV_ALIAS' in \$cfg"
    return 1
  fi
}

wssh() {
  _wssh_base "\$WINDEV_ALIAS"
}

wcmd() {
  if [ \$# -eq 0 ]; then
    echo "Usage: wcmd <powershell command>"
    return 1
  fi
  _wps "\$*"
}

wproj() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; Get-Location"
}

wstatus() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; git status -sb; git branch --show-current"
}

wpull() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; git pull --ff-only"
}

wctl() {
  local action="\${1:-status}"
  local target="\${2:-all}"
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\05_phone_process_control.ps1' -Action '\$action' -Target '\$target' -ProjectPath '\$WINDEV_PROJECT_WIN'"
}

wstart() {
  wctl start "\${1:-all}"
}

wstop() {
  wctl stop "\${1:-all}"
}

wrestart() {
  wctl restart "\${1:-all}"
}

wps() {
  wctl status all
}

wtail() {
  local sel="\${1:-worker}"
  local file
  case "\$sel" in
    backend) file="backend.log" ;;
    worker) file="worker.log" ;;
    bot) file="bot.log" ;;
    *) file="\$sel" ;;
  esac
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; Get-Content '.\\\\logs\\\\\$file' -Tail 120 -Wait"
}

wlogs() {
  wtail "\$@"
}

wdiag() {
  echo "=== HOST ==="
  wcmd "hostname; whoami"
  echo
  echo "=== GIT ==="
  wstatus
  echo
  echo "=== SERVICES ==="
  wps
  echo
  echo "=== SMOKE ==="
  wsmoke
}

wvibe() {
  if [ \$# -eq 0 ]; then
    wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\06_run_vibe_wrapper.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -UvBinPath '\$WINDEV_UV_BIN'"
    return
  fi

  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 command not found in Termux"
    return 1
  fi

  local task="\$*"
  local task_b64
  task_b64="$(printf '%s' "\$task" | base64 | tr -d '\r\n')"
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; \\\$task=[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('\$task_b64')); powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\06_run_vibe_wrapper.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -UvBinPath '\$WINDEV_UV_BIN' -Task \\\$task"
}

waider() {
  wcmd "\\\$env:Path='\$WINDEV_UV_BIN;' + \\\$env:Path; Set-Location '\$WINDEV_PROJECT_WIN'; aider"
}

wtest() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; .\\\\.venv\\\\Scripts\\\\python.exe -m unittest discover -s tests -p 'test_*.py' -v"
}

wmetrics() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; .\\\\.venv\\\\Scripts\\\\python.exe scripts\\\\metrics_report.py --minutes 60"
}

wdevstatus() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; .\\\\.venv\\\\Scripts\\\\python.exe scripts\\\\dev_status.py"
}

wsmoke() {
  wcmd "Set-Location '\$WINDEV_PROJECT_WIN'; .\\\\.venv\\\\Scripts\\\\python.exe scripts\\\\dev_status.py"
  wcmd "try { Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Compress } catch { Write-Host 'health: unavailable' }"
  wcmd "try { Invoke-RestMethod 'http://127.0.0.1:8000/metrics/summary?window_minutes=60' | ConvertTo-Json -Compress } catch { Write-Host 'metrics: unavailable' }"
}

wdeploy() {
  local dry_run=0
  local force_yes=0
  for arg in "\$@"; do
    case "\$arg" in
      --dry-run) dry_run=1 ;;
      --yes) force_yes=1 ;;
      *)
        echo "Unknown option: \$arg"
        echo "Usage: wdeploy [--dry-run] [--yes]"
        return 1
        ;;
    esac
  done

  echo "[plan] 1) wpull"
  echo "[plan] 2) wtest"
  echo "[plan] 3) wrestart all"
  echo "[plan] 4) wsmoke"

  if [ "\$dry_run" -eq 1 ]; then
    return 0
  fi

  if [ "\$force_yes" -ne 1 ]; then
    _confirm "Запустить deploy-цикл?" || return 1
  fi

  wpull || return 1
  wtest || return 1
  wrestart all || return 1
  wsmoke
}

wrun() {
  local mode="\${1:-}"
  case "\$mode" in
    monitor)
      wps
      wmetrics
      ;;
    incident)
      wdiag
      wtail worker
      ;;
    recover)
      wrestart all
      wsmoke
      wstatus
      ;;
    release)
      wstatus
      wdeploy
      ;;
    *)
      echo "Usage: wrun [monitor|incident|recover|release]"
      return 1
      ;;
  esac
}
$BASH_BLOCK_END
EOF

echo
echo "Toolkit installed."
echo "Run: source ~/.bashrc"
echo "Run: whelp"
