#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Usage:
#   bash 02_add_aliases.sh [windows_user] [windows_host] [host_alias] [project_win_path] [uv_bin_win_path] [termux_repo_path]
#
# Example:
#   bash 02_add_aliases.sh MiBookPro 192.168.0.135 windev "C:\Users\MiBookPro\PycharmProjects\PythonProject" "C:\Users\MiBookPro\.local\bin" "$HOME/iikoinvoicebot"

WIN_USER="${1:-MiBookPro}"
WIN_HOST="${2:-192.168.0.135}"
HOST_ALIAS="${3:-windev}"
WIN_PROJECT="${4:-C:\Users\MiBookPro\PycharmProjects\PythonProject}"
WIN_UV_BIN="${5:-C:\Users\MiBookPro\.local\bin}"
TERMUX_REPO="${6:-$HOME/iikoinvoicebot}"

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
export WINDEV_TERMUX_REPO="$TERMUX_REPO"

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
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new(\$false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); \$OutputEncoding=[Console]::OutputEncoding; chcp 65001 > \$null;'
  _wssh_base "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "\$utf8_prelude \$cmd"
}

_wps_tty() {
  local cmd="\$*"
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new(\$false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); \$OutputEncoding=[Console]::OutputEncoding; chcp 65001 > \$null;'
  _wssh_base -tt "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "\$utf8_prelude \$cmd"
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
  wrefresh
    Обновить toolkit: cd repo -> git pull -> install.sh -> source ~/.bashrc
  wstartgo
    Сразу сделать wrefresh и потом открыть wgo.
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
  wvibe
    Старт Vibe с автопрогревом контекста (чтение ключевых docs).
  wvibe reconnect
    Продолжить последнюю сессию после обрыва.
  wvibe --no-bootstrap
    Старт без автопрогрева.
  wvibe mcp "<команда>"
    Выполнить точную команду через MCP bridge и вернуть stdout/stderr/exit_code.
  wvibe "<задача>"
    Старт с автопрогревом + сразу задача.
  wreconnect
    Короткая команда, то же самое что wvibe reconnect.
  wmcp "<команда>"
    Короткая команда, то же самое что wvibe mcp "<команда>".
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

wlocalprep() {
  if [ -z "\${WINDEV_TERMUX_REPO:-}" ] || [ ! -d "\$WINDEV_TERMUX_REPO" ]; then
    echo "[warn] Termux repo is not configured or missing: \$WINDEV_TERMUX_REPO"
    return 0
  fi

  local from_dir="\$PWD"
  cd "\$WINDEV_TERMUX_REPO" || return 1

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[sync] cd \$WINDEV_TERMUX_REPO"
    if ! git pull --ff-only; then
      echo "[warn] git pull failed, continue with current local state"
    fi
  else
    echo "[warn] Not a git repo: \$WINDEV_TERMUX_REPO"
  fi

  cd "\$from_dir" || true
}

wenter() {
  wlocalprep
  _wssh_base -tt "\$WINDEV_ALIAS" "powershell -NoLogo -NoExit -Command \"Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath '\$WINDEV_PROJECT_WIN'\""
}

wgo() {
  if [ "\${WINDEV_SKIP_LOCALPREP_ONCE:-0}" = "1" ]; then
    WINDEV_SKIP_LOCALPREP_ONCE=0
  else
    wlocalprep
  fi
  _wssh_base -tt "\$WINDEV_ALIAS" "powershell -NoLogo -NoExit -Command \"Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath \\\$env:USERPROFILE\""
}

wrefresh() {
  if [ -z "\${WINDEV_TERMUX_REPO:-}" ] || [ ! -d "\$WINDEV_TERMUX_REPO" ]; then
    echo "[error] Termux repo is not configured: \$WINDEV_TERMUX_REPO"
    return 1
  fi

  local from_dir="\$PWD"
  cd "\$WINDEV_TERMUX_REPO" || return 1
  git pull --ff-only || return 1
  bash scripts/termux_ssh_toolkit/termux/install.sh \
    --win-user "\$WINDEV_USER" \
    --win-host "\$WINDEV_HOST" \
    --alias "\$WINDEV_ALIAS" \
    --project "\$WINDEV_PROJECT_WIN" \
    --uv-bin "\$WINDEV_UV_BIN" \
    --termux-repo "\$WINDEV_TERMUX_REPO" \
    --skip-keygen || return 1
  source "\$HOME/.bashrc" || return 1
  cd "\$from_dir" || true
}

wstartgo() {
  wrefresh || return 1
  WINDEV_SKIP_LOCALPREP_ONCE=1
  wgo "\$@"
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
  local mode="start"
  local mcp_cmd=0
  local skip_bootstrap=0
  local force_cleanup=0

  while [ \$# -gt 0 ]; do
    case "\$1" in
      reconnect|rc)
        mode="reconnect"
        shift
        ;;
      ask|text)
        mode="ask"
        shift
        ;;
      stop|kill)
        mode="stop"
        shift
        ;;
      doctor|diag|ps)
        mode="doctor"
        shift
        ;;
      mcp)
        mcp_cmd=1
        shift
        break
        ;;
      --no-bootstrap)
        skip_bootstrap=1
        shift
        ;;
      --force)
        force_cleanup=1
        shift
        ;;
      *)
        break
        ;;
    esac
  done

  local wrapper_ps1="\$WINDEV_PROJECT_WIN\\scripts\\termux_ssh_toolkit\\windows\\06_run_vibe_wrapper.ps1"
  local common_args=(-NoLogo -NoProfile -ExecutionPolicy Bypass -File "\$wrapper_ps1" -ProjectPath "\$WINDEV_PROJECT_WIN" -UvBinPath "\$WINDEV_UV_BIN")
  local force_args=()
  if [ "\$force_cleanup" -eq 1 ]; then
    force_args=(-ForceCleanup)
  fi

  if [ "\$mode" = "stop" ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode stop "\${force_args[@]}"
    return
  fi

  if [ "\$mode" = "doctor" ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode doctor "\${force_args[@]}"
    return
  fi

  if [ "\$mode" = "ask" ] && [ \$# -eq 0 ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode ask "\${force_args[@]}"
    return
  fi

  if [ "\$mode" = "reconnect" ]; then
    _wssh_base -tt "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode reconnect "\${force_args[@]}"
    return
  fi

  if [ "\$mcp_cmd" -eq 1 ] && [ \$# -eq 0 ]; then
    echo "Usage: wvibe mcp \"<exact command>\""
    return 1
  fi

  if [ \$# -eq 0 ]; then
    local start_args=(-Mode start)
    if [ "\$skip_bootstrap" -eq 1 ]; then
      start_args+=(-SkipBootstrap)
    fi
    _wssh_base -tt "\$WINDEV_ALIAS" powershell "\${common_args[@]}" "\${start_args[@]}" "\${force_args[@]}"
    return
  fi

  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 command not found in Termux"
    return 1
  fi

  local task="\$*"
  local task_b64
  task_b64="\$(printf '%s' "\$task" | base64 | tr -d '\r\n')"
  if [ "\$mcp_cmd" -eq 1 ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode mcp_cmd "\${force_args[@]}" -TaskBase64 "\$task_b64"
  elif [ "\$mode" = "ask" ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode ask "\${force_args[@]}" -TaskBase64 "\$task_b64"
  else
    local start_args=(-Mode start)
    if [ "\$skip_bootstrap" -eq 1 ]; then
      start_args+=(-SkipBootstrap)
    fi
    _wssh_base -tt "\$WINDEV_ALIAS" powershell "\${common_args[@]}" "\${start_args[@]}" "\${force_args[@]}" -TaskBase64 "\$task_b64"
  fi
}

wreconnect() {
  wvibe reconnect
}

wmcp() {
  wvibe mcp "\$@"
}

wvshell() {
  local shell_ps1="\$WINDEV_PROJECT_WIN\\scripts\\termux_ssh_toolkit\\windows\\09_wvibe_light_shell.ps1"
  _wssh_base -tt "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "\$shell_ps1" -ProjectPath "\$WINDEV_PROJECT_WIN" -UvBinPath "\$WINDEV_UV_BIN"
}

wplan() {
  if [ \$# -eq 0 ]; then
    echo "Usage: wplan <task text>"
    return 1
  fi
  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 command not found in Termux"
    return 1
  fi
  local msg="\$*"
  local msg_b64
  msg_b64="\$(printf '%s' "\$msg" | base64 | tr -d '\r\n')"
  _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action plan -Source 'termux' -Text ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('\$msg_b64')))"
}

wmailbox() {
  local action="\${1:-status}"
  shift || true
  case "\$action" in
    ensure|status|list|digest|show|prompt|handoff)
      _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action '\$action'"
      ;;
    termux|pull)
      if ! _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null; then
        # Backward-compatible path if "termux" action is absent on remote script.
        _wps "Set-Location '\$WINDEV_PROJECT_WIN'; if (Test-Path '.\\\\ops\\\\mailbox\\\\for_termux.md') { Get-Content '.\\\\ops\\\\mailbox\\\\for_termux.md' -Raw -Encoding UTF8 } else { Write-Output '[warn] file not found: .\\\\ops\\\\mailbox\\\\for_termux.md' }"
      fi
      ;;
    pullclip)
      local reply
      if reply="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null)"; then
        :
      else
        reply="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; if (Test-Path '.\\\\ops\\\\mailbox\\\\for_termux.md') { Get-Content '.\\\\ops\\\\mailbox\\\\for_termux.md' -Raw -Encoding UTF8 } else { '' }")"
      fi
      if [ -z "\$reply" ]; then
        echo "[warn] no termux reply found in mailbox."
        return 1
      fi
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "\$reply" | termux-clipboard-set
        echo "[ok] Termux mailbox reply copied to Android clipboard."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "\$reply"
      ;;
    codexclip)
      local prompt
      local default_prompt
      default_prompt=\$'Прочитай файл ops/mailbox/for_codex.md и выполни задачи из него.\nЕсли данных недостаточно, задай до 3 уточняющих вопросов.\nВ ответе: сначала действия и изменения, затем коротко риски и следующий шаг.'
      if prompt="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action handoff" 2>/dev/null)"; then
        :
      else
        prompt=""
      fi
      if [ -z "\$prompt" ]; then
        # Backward-compatible path: works even if remote mailbox script has no "handoff" action yet.
        _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action digest" >/dev/null || return 1
        prompt="\$default_prompt"
      fi
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "\$prompt" | termux-clipboard-set
        echo "[ok] Codex prompt copied to Android clipboard."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "\$prompt"
      ;;
    flow)
      cat <<'FLOW'
wplan "<что сделать>"
wmailbox codexclip
# затем открой Codex и вставь prompt из буфера
FLOW
      ;;
    flowclip)
      local flow_text
      flow_text=\$'wplan "<что сделать>"\nwmailbox codexclip\n# затем открой Codex и вставь prompt из буфера'
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "\$flow_text" | termux-clipboard-set
        echo "[ok] Command pack copied to Android clipboard."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "\$flow_text"
      ;;
    resolve)
      if [ \$# -eq 0 ]; then
        echo "Usage: wmailbox resolve <file1.md> [file2.md ...]"
        return 1
      fi
      local joined=""
      local it
      for it in "\$@"; do
        if [ -n "\$joined" ]; then
          joined="\$joined','"
        fi
        joined="\$joined\$it"
      done
      _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action resolve -Items @('\$joined' -split \"','\")"
      ;;
    *)
      echo "Usage: wmailbox [ensure|status|list|digest|show|termux|pull|pullclip|prompt|handoff|codexclip|flow|flowclip|resolve]"
      return 1
      ;;
  esac
}

_wphone_require_tmux() {
  if command -v tmux >/dev/null 2>&1; then
    return 0
  fi
  echo "[info] tmux not found in Termux, installing..."
  if ! pkg install -y tmux >/dev/null; then
    echo "[error] failed to install tmux via pkg"
    return 1
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    echo "[error] tmux install completed but binary is missing"
    return 1
  fi
}

_wphone_ensure_session() {
  local session_name="\${1:-\${WPHONE_SESSION:-main}}"
  _wphone_require_tmux || return 1
  if ! tmux has-session -t "\$session_name" 2>/dev/null; then
    tmux new-session -d -s "\$session_name" "bash --login" || return 1
    tmux set-option -t "\$session_name" remain-on-exit on >/dev/null 2>&1 || true
  fi
}

wphone() {
  local sub="\${1:-help}"
  shift || true
  local session_name="\${WPHONE_SESSION:-main}"

  case "\$sub" in
    help|-h|--help)
      cat <<'WPHONE_HELP'
Usage: wphone <command>

Commands:
  wphone session [name]   Show/set default tmux session name (default: main)
  wphone init             Ensure tmux is installed and session exists
  wphone ls               List tmux sessions
  wphone attach           Attach to default session
  wphone run "<cmd>"      Send command + Enter to session
  wphone send "<text>"    Send literal text (without Enter)
  wphone paste            Send Android clipboard text + Enter
  wphone capture [lines]  Print last lines from session pane (default: 120)
WPHONE_HELP
      ;;
    session)
      if [ \$# -eq 0 ]; then
        echo "wphone session: \$session_name"
        return 0
      fi
      export WPHONE_SESSION="\$1"
      echo "[ok] default wphone session set: \$WPHONE_SESSION"
      ;;
    init)
      _wphone_ensure_session "\$session_name" || return 1
      echo "[ok] phone tmux session ready: \$session_name"
      echo "Attach with: wphone attach"
      ;;
    list|ls)
      _wphone_require_tmux || return 1
      tmux ls 2>/dev/null || echo "[info] no tmux sessions yet. Run: wphone init"
      ;;
    attach)
      _wphone_ensure_session "\$session_name" || return 1
      tmux attach -t "\$session_name"
      ;;
    run)
      if [ \$# -eq 0 ]; then
        echo "Usage: wphone run <command>"
        return 1
      fi
      local cmd="\$*"
      _wphone_ensure_session "\$session_name" || return 1
      tmux send-keys -t "\$session_name" -l "\$cmd"
      tmux send-keys -t "\$session_name" C-m
      echo "[ok] sent+enter to \$session_name"
      ;;
    send)
      if [ \$# -eq 0 ]; then
        echo "Usage: wphone send <text>"
        return 1
      fi
      local txt="\$*"
      _wphone_ensure_session "\$session_name" || return 1
      tmux send-keys -t "\$session_name" -l "\$txt"
      echo "[ok] sent text to \$session_name"
      ;;
    paste)
      if ! command -v termux-clipboard-get >/dev/null 2>&1; then
        echo "[warn] termux-clipboard-get not found. Install termux-api package and Termux:API app."
        return 1
      fi
      local clip
      clip="\$(termux-clipboard-get)"
      if [ -z "\$clip" ]; then
        echo "[warn] Android clipboard is empty."
        return 1
      fi
      _wphone_ensure_session "\$session_name" || return 1
      tmux send-keys -t "\$session_name" -l "\$clip"
      tmux send-keys -t "\$session_name" C-m
      echo "[ok] sent clipboard to \$session_name"
      ;;
    capture)
      local lines="\${1:-120}"
      case "\$lines" in
        ''|*[!0-9]*)
          echo "Usage: wphone capture [lines:int]"
          return 1
          ;;
      esac
      _wphone_ensure_session "\$session_name" || return 1
      tmux capture-pane -p -S "-\$lines" -t "\$session_name"
      ;;
    *)
      echo "Usage: wphone [help|session|init|ls|attach|run|send|paste|capture]"
      return 1
      ;;
  esac
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

# Unified help source: shared files used by both Termux and Windows wrappers.
_whelp_shared_dir() {
  local default_repo="\${WINDEV_TERMUX_REPO:-\$HOME/iikoinvoicebot}"
  local candidate

  for candidate in \
    "\${WINDEV_TERMUX_REPO:-}/scripts/termux_ssh_toolkit/shared" \
    "\$default_repo/scripts/termux_ssh_toolkit/shared" \
    "\$HOME/iikoinvoicebot/scripts/termux_ssh_toolkit/shared" \
    "\$PWD/scripts/termux_ssh_toolkit/shared"
  do
    if [ -n "\$candidate" ] && [ -f "\$candidate/whelp_ru.txt" ]; then
      echo "\$candidate"
      return 0
    fi
  done

  echo "\$default_repo/scripts/termux_ssh_toolkit/shared"
}

wsets() {
  local sets_file
  sets_file="\$(_whelp_shared_dir)/whelp_sets_ru.txt"
  if [ -f "\$sets_file" ]; then
    cat "\$sets_file"
    return 0
  fi
  echo "Файл наборов команд не найден: \$sets_file"
}

whelp() {
  local topic="\${1:-all}"
  local help_file
  help_file="\$(_whelp_shared_dir)/whelp_ru.txt"

  case "\$topic" in
    sets|set|scenarios|scenario)
      wsets
      return 0
      ;;
  esac

  if [ -f "\$help_file" ]; then
    cat "\$help_file"
    return 0
  fi

  echo "Файл справки не найден: \$help_file"
}

wh() {
  whelp "\$@"
}
$BASH_BLOCK_END
EOF

echo
echo "Toolkit installed."
echo "Run: source ~/.bashrc"
echo "Run: whelp"
