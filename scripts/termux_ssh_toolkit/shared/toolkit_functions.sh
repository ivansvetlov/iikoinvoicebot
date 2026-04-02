#!/bin/bash
# Windev Toolkit Functions
# Auto-generated from install.sh via template substitution
# DO NOT EDIT DIRECTLY - changes will be overwritten on reinstall
# Source this file from ~/.bashrc

# ============================================================================
# CONFIGURATION - Substituted at install time
# ============================================================================

export WINDEV_ALIAS="{{HOST_ALIAS}}"
export WINDEV_USER="{{WIN_USER}}"
export WINDEV_HOST="{{WIN_HOST}}"
export WINDEV_PROJECT_WIN="{{WIN_PROJECT}}"
export WINDEV_UV_BIN="{{WIN_UV_BIN}}"
export WINDEV_TERMUX_REPO="{{TERMUX_REPO}}"

# ============================================================================
# HELPER FUNCTIONS - Base SSH and PowerShell wrappers
# ============================================================================

_wssh_base() {
  ssh \
    -o ControlMaster=no \
    -o ConnectTimeout=5 \
    -o ConnectionAttempts=1 \
    -o BatchMode=yes \
    -o NumberOfPasswordPrompts=0 \
    -o StrictHostKeyChecking=accept-new \
    -o PreferredAuthentications=publickey \
    -o PubkeyAuthentication=yes \
    -o IdentitiesOnly=yes \
    "$@"
}

_wps() {
  local cmd="$*"
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; chcp 65001 > $null;'
  local full_cmd="$utf8_prelude $cmd"
  local raw=""
  local rc=0
  if command -v iconv > /dev/null 2>&1 && command -v base64 > /dev/null 2>&1; then
    local encoded
    encoded="$(printf '%s' "$full_cmd" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\r\n')"
    raw="$(_wssh_base "$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand "$encoded" 2>&1)" || rc=$?
  else
    raw="$(_wssh_base "$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$full_cmd" 2>&1)" || rc=$?
  fi
  printf '%s\n' "$raw" | awk '
    BEGIN { drop=0 }
    /^#< CLIXML/ { next }
    /^<Objs Version=/ { drop=1 }
    drop==1 { if (/<\/Objs>/) { drop=0 }; next }
    { print }
  '
  return $rc
}

_wps_tty() {
  local cmd="$*"
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; chcp 65001 > $null;'
  local full_cmd="$utf8_prelude $cmd"
  if command -v iconv > /dev/null 2>&1 && command -v base64 > /dev/null 2>&1; then
    local encoded
    encoded="$(printf '%s' "$full_cmd" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\r\n')"
    _wssh_base -tt "$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand "$encoded"
  else
    _wssh_base -tt "$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$full_cmd"
  fi
}

_confirm() {
  local prompt="${1:-Продолжить?}"
  read -r -p "$prompt [y/N]: " ans
  case "$ans" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

# ============================================================================
# SSH / HOST FUNCTIONS
# ============================================================================

wfixssh() {
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  [ -f "$HOME/.ssh/id_ed25519" ] && chmod 600 "$HOME/.ssh/id_ed25519"
  [ -f "$HOME/.ssh/id_ed25519.pub" ] && chmod 644 "$HOME/.ssh/id_ed25519.pub"
  rm -f "$HOME/.ssh"/cm-* 2>/dev/null || true
  echo "SSH local state fixed."
  echo "Now test: wssh"
}

wsetip() {
  local ip="${1:-}"
  local cfg="$HOME/.ssh/config"
  if [ -z "$ip" ]; then
    echo "Usage: wsetip <new_windows_ip>"
    return 1
  fi
  if [ ! -f "$cfg" ]; then
    echo "No ~/.ssh/config found"
    return 1
  fi

  if awk -v host="$WINDEV_ALIAS" -v ip="$ip" '
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
    ' "$cfg" > "$cfg.tmp"; then
    mv "$cfg.tmp" "$cfg"
    export WINDEV_HOST="$ip"
    echo "Updated $WINDEV_ALIAS -> $ip"
    echo "Now test: wssh"
  else
    rm -f "$cfg.tmp"
    echo "Could not update host '$WINDEV_ALIAS' in $cfg"
    return 1
  fi
}

wssh() {
  _wssh_base "$WINDEV_ALIAS"
}

wlocalprep() {
  if [ -z "${WINDEV_TERMUX_REPO:-}" ] || [ ! -d "$WINDEV_TERMUX_REPO" ]; then
    echo "[warn] Termux repo is not configured or missing: $WINDEV_TERMUX_REPO"
    return 0
  fi

  local from_dir="$PWD"
  cd "$WINDEV_TERMUX_REPO" || return 1

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[sync] cd $WINDEV_TERMUX_REPO"
    if ! git pull --ff-only; then
      echo "[warn] git pull failed, continue with current local state"
    fi
  else
    echo "[warn] Not a git repo: $WINDEV_TERMUX_REPO"
  fi

  cd "$from_dir" || true
}

wenter() {
  wlocalprep
  _wssh_base -tt "$WINDEV_ALIAS" "powershell -NoLogo -NoExit -Command \"Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath '$WINDEV_PROJECT_WIN'\""
}

wgo() {
  if [ "${WINDEV_SKIP_LOCALPREP_ONCE:-0}" = "1" ]; then
    WINDEV_SKIP_LOCALPREP_ONCE=0
  else
    wlocalprep
  fi
  _wssh_base -tt "$WINDEV_ALIAS" "powershell -NoLogo -NoExit -Command \"Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -Path ~\""
}

wrefresh() {
  if [ -z "${WINDEV_TERMUX_REPO:-}" ] || [ ! -d "$WINDEV_TERMUX_REPO" ]; then
    echo "[error] Termux repo is not configured: $WINDEV_TERMUX_REPO"
    return 1
  fi

  local from_dir="$PWD"
  cd "$WINDEV_TERMUX_REPO" || return 1
  git pull --ff-only || return 1
  bash scripts/termux_ssh_toolkit/termux/install.sh \
    --win-user "$WINDEV_USER" \
    --win-host "$WINDEV_HOST" \
    --alias "$WINDEV_ALIAS" \
    --project "$WINDEV_PROJECT_WIN" \
    --uv-bin "$WINDEV_UV_BIN" \
    --termux-repo "$WINDEV_TERMUX_REPO" \
    --skip-keygen || return 1
  source "$HOME/.bashrc" || return 1
  cd "$from_dir" || true
}

wstartgo() {
  wrefresh || return 1
  WINDEV_SKIP_LOCALPREP_ONCE=1
  wgo "$@"
}

wcmd() {
  if [ $# -eq 0 ]; then
    echo "Usage: wcmd <powershell command>"
    return 1
  fi
  _wps "$*"
}

# ============================================================================
# PROJECT / GIT FUNCTIONS
# ============================================================================

wproj() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; Get-Location"
}

wstatus() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; git status -sb; git branch --show-current"
}

wpull() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; git pull --ff-only"
}

# ============================================================================
# SERVICE CONTROL FUNCTIONS (backend/worker/bot)
# ============================================================================

wctl() {
  local action="${1:-status}"
  local target="${2:-all}"
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\scripts\\termux_ssh_toolkit\\windows\\05_phone_process_control.ps1' -Action '$action' -Target '$target' -ProjectPath '$WINDEV_PROJECT_WIN'"
}

wstart() {
  wctl start "${1:-all}"
}

wstop() {
  wctl stop "${1:-all}"
}

wrestart() {
  wctl restart "${1:-all}"
}

wps() {
  wctl status all
}

wtail() {
  local sel="${1:-worker}"
  local file
  case "$sel" in
    backend) file="backend.log" ;;
    worker) file="worker.log" ;;
    bot) file="bot.log" ;;
    *) file="$sel" ;;
  esac
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; Get-Content '.\\logs\\$file' -Tail 120 -Wait"
}

wlogs() {
  wtail "$@"
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

# ============================================================================
# DIAGNOSTICS & METRICS
# ============================================================================

wdevstatus() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; if (Test-Path '.\\scripts\\termux_ssh_toolkit\\windows\\01_check_dev_status.ps1') { powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\scripts\\termux_ssh_toolkit\\windows\\01_check_dev_status.ps1' -ProjectPath '$WINDEV_PROJECT_WIN' } else { Write-Output '[warn] script not found' }"
}

wsmoke() {
  wdevstatus
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; Invoke-RestMethod http://127.0.0.1:8000/health 2>/dev/null | ConvertTo-Json"
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; Invoke-RestMethod 'http://127.0.0.1:8000/metrics/summary?window_minutes=5' 2>/dev/null | ConvertTo-Json" 2>/dev/null || echo "[warn] /metrics/summary not available"
}

wmetrics() {
  local minutes="${1:-60}"
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; if (Test-Path '.\\scripts\\metrics_report.py') { python '.\\scripts\\metrics_report.py' --minutes $minutes } else { Invoke-RestMethod \"http://127.0.0.1:8000/metrics/summary?window_minutes=$minutes\" 2>/dev/null | ConvertTo-Json }"
}

# ============================================================================
# TESTING & DEPLOYMENT
# ============================================================================

wtest() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; python -m pytest tests/ -v 2>&1 | tail -50"
}

wdeploy() {
  local dry_run=0
  local force_yes=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run)
        dry_run=1
        shift
        ;;
      --yes|-y)
        force_yes=1
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  echo "[plan] 1) wpull"
  echo "[plan] 2) wtest"
  echo "[plan] 3) wrestart all"
  echo "[plan] 4) wsmoke"

  if [ "$dry_run" -eq 1 ]; then
    return 0
  fi

  if [ "$force_yes" -ne 1 ]; then
    _confirm "Запустить deploy-цикл?" || return 1
  fi

  wpull || return 1
  wtest || return 1
  wrestart all || return 1
  wsmoke
}

# ============================================================================
# VIBE / AI AGENT FUNCTIONS
# ============================================================================

wvibe() {
  local mode="start"
  local mcp_cmd=0
  local skip_bootstrap=0
  local force_cleanup=0
  local ask_backend="${WINDEV_WVIBE_ASK_BACKEND:-api}"

  while [ $# -gt 0 ]; do
    case "$1" in
      reconnect|rc)
        mode="reconnect"
        shift
        ;;
      ask|text)
        mode="ask"
        shift
        ;;
      cliask)
        mode="ask"
        ask_backend="cli"
        shift
        ;;
      api)
        mode="api_ask"
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

  # Use forward-slash Windows paths for remote ssh argv stability.
  # Backslashes may be mangled when ssh composes the remote command line.
  local project_ps="${WINDEV_PROJECT_WIN//\\//}"
  local uv_bin_ps="${WINDEV_UV_BIN//\\//}"
  local wrapper_ps1="$project_ps/scripts/termux_ssh_toolkit/windows/06_run_vibe_wrapper.ps1"
  local common_args=(-NoLogo -NoProfile -ExecutionPolicy Bypass -File "$wrapper_ps1" -ProjectPath "$project_ps" -UvBinPath "$uv_bin_ps")
  local force_args=()
  if [ "$force_cleanup" -eq 1 ]; then
    force_args=(-ForceCleanup)
  fi

  if [ "$mode" = "stop" ]; then
    _wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode stop "${force_args[@]}"
    return
  fi

  if [ "$mode" = "doctor" ]; then
    _wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode doctor "${force_args[@]}"
    return
  fi

  if [ "$mode" = "ask" ] && [ $# -eq 0 ]; then
    _wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode ask "${force_args[@]}"
    return
  fi

  if [ "$mode" = "reconnect" ]; then
    _wssh_base -tt "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode reconnect "${force_args[@]}"
    return
  fi

  if [ "$mcp_cmd" -eq 1 ] && [ $# -eq 0 ]; then
    echo "Usage: wvibe mcp \"<exact command>\""
    return 1
  fi

  if [ $# -eq 0 ]; then
    local start_args=(-Mode start)
    if [ "$skip_bootstrap" -eq 1 ]; then
      start_args+=(-SkipBootstrap)
    fi
    _wssh_base -tt "$WINDEV_ALIAS" powershell "${common_args[@]}" "${start_args[@]}" "${force_args[@]}"
    return
  fi

  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 command not found in Termux"
    return 1
  fi

  local task="$*"
  local task_b64
  task_b64="$(printf '%s' "$task" | base64 | tr -d '\r\n')"
  if [ "$mode" = "ask" ] && [ "$ask_backend" = "api" ]; then
    mode="api_ask"
  fi
  if [ "$mcp_cmd" -eq 1 ]; then
    _wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode mcp_cmd "${force_args[@]}" -TaskBase64 "$task_b64"
  elif [ "$mode" = "ask" ]; then
    _wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode ask "${force_args[@]}" -TaskBase64 "$task_b64"
  elif [ "$mode" = "api_ask" ]; then
    local api_raw
    api_raw="$(_wssh_base "$WINDEV_ALIAS" powershell "${common_args[@]}" -Mode api_ask "${force_args[@]}" -TaskBase64 "$task_b64")"
    local api_b64
    api_b64="$(printf '%s' "$api_raw" | base64 | tr -d '\r\n')"
    echo "=== Vibe API Response (base64) ==="
    echo "$api_raw"
  fi
}

wmcp() {
  wvibe mcp "$@"
}

wreconnect() {
  wvibe reconnect "$@"
}

waider() {
  wcmd "Set-Location '$WINDEV_PROJECT_WIN'; aider"
}

# ============================================================================
# PHONE / TMUX FUNCTIONS
# ============================================================================

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
  local session_name="${1:-${WPHONE_SESSION:-main}}"
  _wphone_require_tmux || return 1
  if ! tmux has-session -t "$session_name" 2>/dev/null; then
    tmux new-session -d -s "$session_name" "bash --login" || return 1
    tmux set-option -t "$session_name" remain-on-exit on >/dev/null 2>&1 || true
  fi
}

wphone() {
  local sub="${1:-help}"
  shift || true
  local session_name="${WPHONE_SESSION:-main}"

  case "$sub" in
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
      if [ $# -eq 0 ]; then
        echo "wphone session: $session_name"
        return 0
      fi
      export WPHONE_SESSION="$1"
      echo "[ok] default wphone session set: $WPHONE_SESSION"
      ;;
    init)
      _wphone_ensure_session "$session_name" || return 1
      echo "[ok] phone tmux session ready: $session_name"
      echo "Attach with: wphone attach"
      ;;
    list|ls)
      _wphone_require_tmux || return 1
      tmux ls 2>/dev/null || echo "[info] no tmux sessions yet. Run: wphone init"
      ;;
    attach)
      _wphone_ensure_session "$session_name" || return 1
      tmux attach -t "$session_name"
      ;;
    run)
      if [ $# -eq 0 ]; then
        echo "Usage: wphone run <command>"
        return 1
      fi
      local cmd="$*"
      _wphone_ensure_session "$session_name" || return 1
      tmux send-keys -t "$session_name" -l "$cmd"
      tmux send-keys -t "$session_name" C-m
      echo "[ok] sent+enter to $session_name"
      ;;
    send)
      if [ $# -eq 0 ]; then
        echo "Usage: wphone send <text>"
        return 1
      fi
      local txt="$*"
      _wphone_ensure_session "$session_name" || return 1
      tmux send-keys -t "$session_name" -l "$txt"
      echo "[ok] sent text to $session_name"
      ;;
    paste)
      if ! command -v termux-clipboard-get >/dev/null 2>&1; then
        echo "[warn] termux-clipboard-get not found. Install termux-api package and Termux:API app."
        return 1
      fi
      local clip
      clip="$(termux-clipboard-get)"
      if [ -z "$clip" ]; then
        echo "[warn] Android clipboard is empty."
        return 1
      fi
      _wphone_ensure_session "$session_name" || return 1
      tmux send-keys -t "$session_name" -l "$clip"
      tmux send-keys -t "$session_name" C-m
      echo "[ok] sent clipboard to $session_name"
      ;;
    capture)
      local lines="${1:-120}"
      case "$lines" in
        ''|*[!0-9]*)
          echo "Usage: wphone capture [lines:int]"
          return 1
          ;;
      esac
      _wphone_ensure_session "$session_name" || return 1
      tmux capture-pane -p -S "-$lines" -t "$session_name"
      ;;
    *)
      echo "Usage: wphone [help|session|init|ls|attach|run|send|paste|capture]"
      return 1
      ;;
  esac
}

# ============================================================================
# MAILBOX FUNCTIONS
# ============================================================================

_wmailbox_push_text() {
  local text_payload="$1"
  local src_tag="${2:-termux}"
  local text_b64
  local mailbox_ps1="$WINDEV_PROJECT_WIN\\scripts\\termux_ssh_toolkit\\windows\\10_mailbox.ps1"
  text_b64="$(printf '%s' "$text_payload" | base64 | tr -d '\r\n')"
  _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action inbox -Source '$src_tag' -Text ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('$text_b64')))"
}

wmailbox() {
  local action="${1:-status}"
  local mailbox_ps1="$WINDEV_PROJECT_WIN\\scripts\\termux_ssh_toolkit\\windows\\10_mailbox.ps1"
  local for_termux_path="$WINDEV_PROJECT_WIN\\ops\\mailbox\\for_termux.md"
  shift || true
  case "$action" in
    ensure|status|list|digest|show|prompt|handoff)
      _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action '$action'"
      ;;
    inbox|push)
      local inbox_text=""
      if [ $# -gt 0 ]; then
        inbox_text="$*"
      else
        inbox_text="$(cat)"
      fi
      _wmailbox_push_text "$inbox_text" "termux"
      ;;
    pushlast)
      local last_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wrunbox_last.txt"
      if [ ! -f "$last_file" ]; then
        echo "[warn] no last runbox output found: $last_file"
        return 1
      fi
      _wmailbox_push_text "$(cat "$last_file")" "termux"
      ;;
    termux|pull)
      if ! _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null; then
        _wps "if (Test-Path '$for_termux_path') { Get-Content '$for_termux_path' -Raw -Encoding UTF8 } else { Write-Output '[warn] file not found: .\\ops\\mailbox\\for_termux.md' }"
      fi
      ;;
    pullclip)
      local reply
      local clip_mode="${1:-body}"
      local clip_text=""
      local pull_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/for_termux_pullclip.md"
      local fetched_via_ssh=0
      if _wssh_base "$WINDEV_ALIAS" "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); Get-Content -Raw -Encoding UTF8 '$for_termux_path'\"" > "$pull_file" 2>/dev/null; then
        reply="$(cat "$pull_file" 2>/dev/null || true)"
        fetched_via_ssh=1
      fi
      if [ -z "$reply" ] || [[ "$reply" == "[warn] file not found:"* ]]; then
        if reply="$(_wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null)"; then
          :
        else
          reply=""
        fi
      fi
      if [ -z "$reply" ] || [[ "$reply" == "[warn] file not found:"* ]]; then
        if reply="$(_wps "if (Test-Path '$for_termux_path') { Get-Content '$for_termux_path' -Raw -Encoding UTF8 } else { '' }" 2>/dev/null)"; then
          :
        else
          reply=""
        fi
      fi
      if [ "$fetched_via_ssh" -eq 0 ]; then
        echo "[warn] pullclip: ssh fetch failed, fallback path used."
      fi
      if [ -z "$reply" ]; then
        echo "[warn] no termux reply found in mailbox."
        return 1
      fi
      case "$clip_mode" in
        body)
          clip_text="$(printf '%s' "$reply" | awk 'f{print} /^Source:[[:space:]].*$/{f=1}' | sed '/./,$/!d')"
          if [ -z "$clip_text" ]; then
            clip_text="$reply"
          fi
          ;;
        full)
          clip_text="$reply"
          ;;
        *)
          echo "Usage: wmailbox pullclip [body|full]"
          return 1
          ;;
      esac
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "$clip_text" | termux-clipboard-set
        echo "[ok] Termux mailbox reply copied to Android clipboard ($clip_mode)."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "$clip_text"
      ;;
    reply)
      if [ $# -eq 0 ]; then
        echo "Usage: wmailbox reply <text>"
        return 1
      fi
      if ! command -v base64 >/dev/null 2>&1; then
        echo "base64 command not found in Termux"
        return 1
      fi
      local reply_msg="$*"
      local reply_b64
      reply_b64="$(printf '%s' "$reply_msg" | base64 | tr -d '\r\n')"
      _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action reply -Source 'termux' -Text ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('$reply_b64')))"
      ;;
    watch)
      local interval="${1:-5}"
      case "$interval" in
        ''|*[!0-9]*)
          echo "Usage: wmailbox watch [interval_seconds:int]"
          return 1
          ;;
      esac
      if [ "$interval" -lt 1 ]; then
        interval=1
      fi
      echo "[watch] polling ops/mailbox/for_termux.md every ${interval}s (Ctrl+C to stop)"
      local last_sig=""
      local initialized=0
      while true; do
        local current_reply=""
        local is_valid=0
        if current_reply="$(_wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null)"; then
          if [ -z "$current_reply" ] || [[ "$current_reply" == "[warn] file not found:"* ]]; then
            current_reply="$(_wps "if (Test-Path '$for_termux_path') { Get-Content '$for_termux_path' -Raw -Encoding UTF8 } else { '' }")"
          fi
        else
          current_reply="$(_wps "if (Test-Path '$for_termux_path') { Get-Content '$for_termux_path' -Raw -Encoding UTF8 } else { '' }")"
        fi
        if [[ "$current_reply" == *"# Termux Mailbox"* ]]; then
          is_valid=1
        fi
        if [ "$is_valid" -eq 0 ]; then
          local fallback_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/for_termux_watch.md"
          if _wssh_base "$WINDEV_ALIAS" "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \"Get-Content -Raw -Encoding UTF8 '$WINDEV_PROJECT_WIN\\ops\\mailbox\\for_termux.md'\"" > "$fallback_file" 2>/dev/null; then
            current_reply="$(cat "$fallback_file" 2>/dev/null || true)"
          fi
        fi
        local current_sig
        current_sig="$(printf '%s' "$current_reply" | cksum)"
        if [ "$initialized" -eq 0 ]; then
          initialized=1
          last_sig="$current_sig"
        elif [ "$current_sig" != "$last_sig" ]; then
          last_sig="$current_sig"
          echo
          echo "----- [$(date '+%Y-%m-%d %H:%M:%S')] mailbox update -----"
          printf '%s\n' "$current_reply"
          if command -v termux-clipboard-set >/dev/null 2>&1; then
            printf '%s' "$current_reply" | termux-clipboard-set
            echo "[watch] reply copied to Android clipboard."
          fi
          if command -v termux-notification >/dev/null 2>&1; then
            termux-notification --title "Mailbox update" --content "New reply in for_termux.md" >/dev/null 2>&1 || true
          fi
        fi
        sleep "$interval"
      done
      ;;
    codexclip)
      local prompt
      local default_prompt
      default_prompt="Read ops/mailbox/for_codex.md and execute the tasks from it. If context is insufficient, ask up to 3 clarifying questions. In the answer: actions and changes first, then short risks and next step."
      if prompt="$(_wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action handoff" 2>/dev/null)"; then
        :
      else
        prompt=""
      fi
      if [ -z "$prompt" ]; then
        _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action digest" >/dev/null || return 1
        prompt="$default_prompt"
      fi
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "$prompt" | termux-clipboard-set
        echo "[ok] Codex prompt copied to Android clipboard."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "$prompt"
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
      flow_text="wplan \"<what to do>\"
wmailbox codexclip
# then open Codex and paste the prompt from clipboard"
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "$flow_text" | termux-clipboard-set
        echo "[ok] Command pack copied to Android clipboard."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "$flow_text"
      ;;
    resolve)
      if [ $# -eq 0 ]; then
        echo "Usage: wmailbox resolve <file1.md> [file2.md ...]"
        return 1
      fi
      local joined=""
      local it
      for it in "$@"; do
        if [ -n "$joined" ]; then
          joined="$joined','"
        fi
        joined="$joined$it"
      done
      _wps "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '$mailbox_ps1' -ProjectPath '$WINDEV_PROJECT_WIN' -Action resolve -Items @('$joined' -split \"','\")"
      ;;
    *)
      echo "Usage: wmailbox [ensure|status|list|digest|show|termux|pull|pullclip|reply|watch|prompt|handoff|codexclip|flow|flowclip|resolve|inbox|push|pushlast]"
      return 1
      ;;
  esac
}

wrunbox() {
  if [ $# -eq 0 ]; then
    echo "Usage: wrunbox <command>"
    return 1
  fi
  local cmd="$*"
  local out_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wrunbox_last.txt"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"

  echo "[runbox] $cmd"
  { eval "$cmd"; } > "$out_file" 2>&1
  local rc=$?
  cat "$out_file"

  local cwd
  cwd="$PWD"
  local report
  report="[runbox]
time: $ts
cwd: $cwd
command: $cmd
exit_code: $rc

output:
$(cat "$out_file")"
  _wmailbox_push_text "$report" "termux-runbox" >/dev/null || true
  echo "[ok] run output pushed to ops/mailbox/inbox/LATEST.md"
  return $rc
}

wring() {
  local raw_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wring_cmd_raw.md"
  local cmd_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wring_cmd.sh"
  local out_file="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wring_out.log"
  local run_rc=0
  local push_ok=false

  # Step 1: Fetch command from mailbox
  if ! wmailbox termux > "$raw_file" 2>/dev/null; then
    echo "[error] wring: failed to fetch command block from mailbox"
    return 1
  fi

  # Extract executable body from mailbox markdown and normalize CRLF.
  # Supports both full mailbox format and raw command payloads.
  awk '
    { sub(/\r$/, "") }
    {
      if (!in_body) {
        if ($0 ~ /^# Termux Mailbox[[:space:]]*$/) next
        if ($0 ~ /^Generated:[[:space:]]/) next
        if ($0 ~ /^Source:[[:space:]]/) next
        if ($0 ~ /^[[:space:]]*$/) next
        in_body=1
      }
      print
    }
  ' "$raw_file" > "$cmd_file"

  if [ ! -s "$cmd_file" ]; then
    echo "[error] wring: command block is empty"
    return 1
  fi

  # Step 2: Execute command
  local cmd_summary
  cmd_summary="$(awk 'NF {print; exit}' "$cmd_file" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -z "$cmd_summary" ]; then
    cmd_summary="<empty>"
  fi
  echo "[wring-exec] Running: $cmd_summary"
  bash "$cmd_file" 2>&1 | tee "$out_file"
  run_rc=${PIPESTATUS[0]}

  # Step 3: Push result to mailbox
  if cat "$out_file" | wmailbox inbox >/dev/null 2>&1; then
    push_ok=true
  fi

  # Step 4: Print machine-readable result (always)
  echo "[wring-result] run_rc=$run_rc push_status=$([ "$push_ok" = true ] && echo ok || echo failed) inbox=ops/mailbox/inbox"

  # Step 5: Human-readable message + return code decision
  if [ "$push_ok" = true ]; then
    if [ "$run_rc" -eq 0 ]; then
      echo "[ok] wring: command succeeded and result pushed to mailbox"
      return 0
    else
      echo "[warn] wring: command exited with code $run_rc, but result was pushed to mailbox"
      return "$run_rc"
    fi
  else
    # Critical: data loss scenario
    echo "[error] wring: command exited with code $run_rc AND failed to push result to mailbox (DATA LOSS)"
    return 1
  fi
}

wclip() {
  if ! command -v termux-clipboard-set >/dev/null 2>&1; then
    echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
    return 1
  fi
  local payload=""
  if [ $# -gt 0 ]; then
    payload="$*"
  else
    payload="$(cat)"
  fi
  if [ -z "$payload" ]; then
    echo "[warn] empty payload, nothing copied."
    return 1
  fi
  printf '%s' "$payload" | termux-clipboard-set
  echo "[ok] copied to Android clipboard."
}

wpaste() {
  wmailbox pullclip "$@"
}

# ============================================================================
# SCENARIO & PLANNING FUNCTIONS
# ============================================================================

wplan() {
  if [ $# -eq 0 ]; then
    echo "Usage: wplan \"<task description>\""
    return 1
  fi
  local task="$*"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  local plan_text="[plan] $ts
task: $task"
  _wmailbox_push_text "$plan_text" "termux-plan" >/dev/null || true
  echo "[ok] plan pushed to mailbox inbox."
}

wrun() {
  local mode="${1:-}"
  case "$mode" in
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

# ============================================================================
# HELP FUNCTIONS
# ============================================================================

_whelp_shared_dir() {
  local default_repo="${WINDEV_TERMUX_REPO:-$HOME/iikoinvoicebot}"
  local candidate

  for candidate in \
    "${WINDEV_TERMUX_REPO:-}/scripts/termux_ssh_toolkit/shared" \
    "$default_repo/scripts/termux_ssh_toolkit/shared" \
    "$HOME/iikoinvoicebot/scripts/termux_ssh_toolkit/shared" \
    "$PWD/scripts/termux_ssh_toolkit/shared"
  do
    if [ -n "$candidate" ] && [ -f "$candidate/whelp_ru.txt" ]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$default_repo/scripts/termux_ssh_toolkit/shared"
}

wsets() {
  local sets_file
  sets_file="$(_whelp_shared_dir)/whelp_sets_ru.txt"
  if [ -f "$sets_file" ]; then
    cat "$sets_file"
    return 0
  fi
  echo "Файл наборов команд не найден: $sets_file"
}

whelp() {
  local topic="${1:-all}"
  local help_file
  help_file="$(_whelp_shared_dir)/whelp_ru.txt"

  case "$topic" in
    sets|set|scenarios|scenario)
      wsets
      return 0
      ;;
  esac

  if [ -f "$help_file" ]; then
    cat "$help_file"
    return 0
  fi

  echo "Файл справки не найден: $help_file"
}

wh() {
  whelp "$@"
}

# ============================================================================
# End of toolkit functions
# ============================================================================
