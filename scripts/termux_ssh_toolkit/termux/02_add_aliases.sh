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

cat >> "$BASHRC" <<__WINDEV_BASH_BLOCK__
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
    -o BatchMode=yes \
    -o NumberOfPasswordPrompts=0 \
    -o StrictHostKeyChecking=accept-new \
    -o PreferredAuthentications=publickey \
    -o PubkeyAuthentication=yes \
    -o IdentitiesOnly=yes \
    "\$@"
}

_wps() {
  local cmd="\$*"
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new(\$false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); \$OutputEncoding=[Console]::OutputEncoding; chcp 65001 > \$null;'
  local full_cmd="\$utf8_prelude \$cmd"
  local raw=""
  local rc=0
  if command -v iconv > /dev/null 2>&1 && command -v base64 > /dev/null 2>&1; then
    local encoded
    encoded="\$(printf '%s' "\$full_cmd" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\r\n')"
    raw="\$(_wssh_base "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand "\$encoded" 2>&1)" || rc=\$?
  else
    raw="\$(_wssh_base "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "\$full_cmd" 2>&1)" || rc=\$?
  fi
  printf '%s\n' "\$raw" | awk '
    BEGIN { drop=0 }
    /^#< CLIXML/ { next }
    /^<Objs Version=/ { drop=1 }
    drop==1 { if (/<\/Objs>/) { drop=0 }; next }
    { print }
  '
  return \$rc
}

_wps_tty() {
  local cmd="\$*"
  local utf8_prelude='[Console]::InputEncoding=[System.Text.UTF8Encoding]::new(\$false); [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); \$OutputEncoding=[Console]::OutputEncoding; chcp 65001 > \$null;'
  local full_cmd="\$utf8_prelude \$cmd"
  if command -v iconv > /dev/null 2>&1 && command -v base64 > /dev/null 2>&1; then
    local encoded
    encoded="\$(printf '%s' "\$full_cmd" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\r\n')"
    _wssh_base -tt "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand "\$encoded"
  else
    _wssh_base -tt "\$WINDEV_ALIAS" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "\$full_cmd"
  fi
}

_confirm() {
  local prompt="\${1:-РџСЂРѕРґРѕР»Р¶РёС‚СЊ?}"
  read -r -p "\$prompt [y/N]: " ans
  case "\$ans" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

wsets() {
  cat <<'SETS'
РќРђР‘РћР Р« РљРћРњРђРќР” (РіРѕС‚РѕРІС‹Рµ СЃС†РµРЅР°СЂРёРё)

1) РќР°С‡Р°Р»Рѕ РґРЅСЏ:
   wps
   wstatus
   wdevstatus

2) Р—Р°РїСѓСЃРє РІСЃРµРіРѕ СЃС‚РµРєР°:
   wstart all
   wps
   wtail backend

3) РџРѕСЃР»Рµ РїСЂР°РІРѕРє РІ РєРѕРґРµ:
   wtest
   wrestart all
   wsmoke

4) Р”РµРїР»РѕР№-РїСЂРѕС…РѕРґ:
   wdeploy --dry-run
   wdeploy --yes

5) РђРІР°СЂРёР№РЅС‹Р№ СЂРµР¶РёРј:
   wrun incident

6) Р’РѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ:
   wrun recover

7) Р РµР»РёР·РЅС‹Р№ РїСЂРѕРіРѕРЅ:
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
РўР•Р›Р•Р¤РћРќ -> РџРљ: РџРћР›РќР«Р™ РЎРџР РђР’РћР§РќРРљ

Р§С‚Рѕ СЌС‚Рѕ:
  РўС‹ РІ Termux РЅР° С‚РµР»РµС„РѕРЅРµ.
  Р›СЋР±Р°СЏ РєРѕРјР°РЅРґР° w* РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ РЅР° Windows-РџРљ РїРѕ SSH.

Р‘С‹СЃС‚СЂС‹Р№ СЃС‚Р°СЂС‚ (РјРёРЅРёРјСѓРј):
  1) wstatus
  2) wtest
  3) wdeploy --yes
  4) wtail worker

РЎР’РЇР—Р¬ Р Р‘РђР—Рђ:
  whelp
    РџРѕР»РЅР°СЏ СЃРїСЂР°РІРєР° (СЌС‚РѕС‚ СЌРєСЂР°РЅ).
  whelp sets
    РўРѕР»СЊРєРѕ РіРѕС‚РѕРІС‹Рµ РЅР°Р±РѕСЂС‹ РєРѕРјР°РЅРґ.
  wrefresh
    РћР±РЅРѕРІРёС‚СЊ toolkit: cd repo -> git pull -> install.sh -> source ~/.bashrc
  wstartgo
    РЎСЂР°Р·Сѓ СЃРґРµР»Р°С‚СЊ wrefresh Рё РїРѕС‚РѕРј РѕС‚РєСЂС‹С‚СЊ wgo.
  wfixssh
    Р›РѕРєР°Р»СЊРЅРѕ С‡РёРЅРёС‚ SSH-РїСЂР°РІР°/СЃРѕРєРµС‚С‹ РІ Termux.
  wsetip <ip_РїРє>
    РћР±РЅРѕРІРёС‚СЊ IP РІ ~/.ssh/config РґР»СЏ alias.
  wssh
    РћС‚РєСЂС‹С‚СЊ РѕР±С‹С‡РЅСѓСЋ SSH-СЃРµСЃСЃРёСЋ РЅР° РџРљ.
  wcmd "<PowerShell-РєРѕРјР°РЅРґР°>"
    Р’С‹РїРѕР»РЅРёС‚СЊ РѕРґРЅСѓ РєРѕРјР°РЅРґСѓ РЅР° РџРљ.
    РџСЂРёРјРµСЂ: wcmd "Get-Date"

РџР РћР•РљРў Р GIT:
  wproj
    РџРѕРєР°Р·Р°С‚СЊ РїСѓС‚СЊ РїСЂРѕРµРєС‚Р° РЅР° РџРљ.
  wstatus
    git status -sb + С‚РµРєСѓС‰Р°СЏ РІРµС‚РєР°.
  wpull
    Р‘РµР·РѕРїР°СЃРЅРѕ РѕР±РЅРѕРІРёС‚СЊ РІРµС‚РєСѓ: git pull --ff-only.

РЎР•Р Р’РРЎР« (backend/worker/bot):
  wstart [all|backend|worker|bot]
    Р—Р°РїСѓСЃС‚РёС‚СЊ СЃРµСЂРІРёСЃ(С‹).
  wstop [all|backend|worker|bot]
    РћСЃС‚Р°РЅРѕРІРёС‚СЊ СЃРµСЂРІРёСЃ(С‹).
  wrestart [all|backend|worker|bot]
    РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ СЃРµСЂРІРёСЃ(С‹).
  wps
    РџРѕРєР°Р·Р°С‚СЊ up/down + pid РїРѕ РІСЃРµРј СЃРµСЂРІРёСЃР°Рј.

Р›РћР“Р Р Р”РРђР“РќРћРЎРўРРљРђ:
  wtail [backend|worker|bot|file.log]
    РЎРјРѕС‚СЂРµС‚СЊ live-Р»РѕРі.
    РџСЂРёРјРµСЂС‹:
      wtail worker
      wtail backend
      wtail backend.out.log
  wlogs [...]
    РўРѕ Р¶Рµ СЃР°РјРѕРµ, Р°Р»РёР°СЃ Рє wtail.
  wdevstatus
    РџСЂРѕРІРµСЂРєР° dev-РѕРєСЂСѓР¶РµРЅРёСЏ.
  wmetrics
    РћС‚С‡РµС‚ РїРѕ РјРµС‚СЂРёРєР°Рј (РѕРєРЅРѕ 60 РјРёРЅСѓС‚).
  wsmoke
    Р‘С‹СЃС‚СЂР°СЏ РїСЂРѕРІРµСЂРєР°: dev_status + /health + /metrics/summary.
  wdiag
    РћРґРёРЅ СЌРєСЂР°РЅ: host + git + services + smoke.

РўР•РЎРўР« Р Р”Р•РџР›РћР™:
  wtest
    Р—Р°РїСѓСЃРє unittest.
  wdeploy [--dry-run] [--yes]
    Р Р°Р±РѕС‡РёР№ С†РёРєР»:
      1) pull
      2) test
      3) restart all
      4) smoke
    --dry-run: С‚РѕР»СЊРєРѕ РїРѕРєР°Р·Р°С‚СЊ РїР»Р°РЅ.
    --yes: РІС‹РїРѕР»РЅРёС‚СЊ Р±РµР· РІРѕРїСЂРѕСЃР°.

РђР“Р•РќРўР«:
  wvibe
    РЎС‚Р°СЂС‚ Vibe СЃ Р°РІС‚РѕРїСЂРѕРіСЂРµРІРѕРј РєРѕРЅС‚РµРєСЃС‚Р° (С‡С‚РµРЅРёРµ РєР»СЋС‡РµРІС‹С… docs).
  wvibe reconnect
    РџСЂРѕРґРѕР»Р¶РёС‚СЊ РїРѕСЃР»РµРґРЅСЋСЋ СЃРµСЃСЃРёСЋ РїРѕСЃР»Рµ РѕР±СЂС‹РІР°.
  wvibe --no-bootstrap
    РЎС‚Р°СЂС‚ Р±РµР· Р°РІС‚РѕРїСЂРѕРіСЂРµРІР°.
  wvibe mcp "<РєРѕРјР°РЅРґР°>"
    Р’С‹РїРѕР»РЅРёС‚СЊ С‚РѕС‡РЅСѓСЋ РєРѕРјР°РЅРґСѓ С‡РµСЂРµР· MCP bridge Рё РІРµСЂРЅСѓС‚СЊ stdout/stderr/exit_code.
  wvibe "<Р·Р°РґР°С‡Р°>"
    РЎС‚Р°СЂС‚ СЃ Р°РІС‚РѕРїСЂРѕРіСЂРµРІРѕРј + СЃСЂР°Р·Сѓ Р·Р°РґР°С‡Р°.
  wreconnect
    РљРѕСЂРѕС‚РєР°СЏ РєРѕРјР°РЅРґР°, С‚Рѕ Р¶Рµ СЃР°РјРѕРµ С‡С‚Рѕ wvibe reconnect.
  wmcp "<РєРѕРјР°РЅРґР°>"
    РљРѕСЂРѕС‚РєР°СЏ РєРѕРјР°РЅРґР°, С‚Рѕ Р¶Рµ СЃР°РјРѕРµ С‡С‚Рѕ wvibe mcp "<РєРѕРјР°РЅРґР°>".
  waider
    Р—Р°РїСѓСЃС‚РёС‚СЊ aider РІ РїСЂРѕРµРєС‚Рµ (РµСЃР»Рё СѓСЃС‚Р°РЅРѕРІР»РµРЅ).

Р“РћРўРћР’Р«Р• РЎР¦Р•РќРђР РР:
  wrun monitor
    РЎС‚Р°С‚СѓСЃ + РјРµС‚СЂРёРєРё.
  wrun incident
    РџРѕР»РЅР°СЏ РґРёР°РіРЅРѕСЃС‚РёРєР° + live-Р»РѕРі worker.
  wrun recover
    РџРµСЂРµР·Р°РїСѓСЃРє РІСЃРµРіРѕ + smoke + status.
  wrun release
    РЎС‚Р°С‚СѓСЃ + deploy-С†РёРєР».

Р•РЎР›Р РќР• Р РђР‘РћРўРђР•Рў:
  1) "command not found: whelp"
     Р’С‹РїРѕР»РЅРё: source ~/.bashrc
  2) SSH timeout
     РћР±РЅРѕРІРё IP: wsetip <РЅРѕРІС‹Р№_ip_РїРє>
     РџСЂРѕРІРµСЂСЊ РїРѕСЂС‚: ncat <ip_РїРє> 22
     РџРѕС‚РѕРј: ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes <user>@<ip_РїРє>
  3) РљР»СЋС‡ РїСЂРѕСЃРёС‚ РїР°СЂРѕР»СЊ
     Р—Р°РїСѓСЃС‚Рё: wfixssh

Р”Р»СЏ СЃС†РµРЅР°СЂРёРµРІ РѕРґРЅРѕР№ РєРѕРјР°РЅРґРѕР№:
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
  local ask_backend="${WINDEV_WVIBE_ASK_BACKEND:-api}"

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
  if [ "\$mode" = "ask" ] && [ "\$ask_backend" = "api" ]; then
    mode="api_ask"
  fi
  if [ "\$mcp_cmd" -eq 1 ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode mcp_cmd "\${force_args[@]}" -TaskBase64 "\$task_b64"
  elif [ "\$mode" = "ask" ]; then
    _wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode ask "\${force_args[@]}" -TaskBase64 "\$task_b64"
  elif [ "\$mode" = "api_ask" ]; then
    local api_raw
    api_raw="\$(_wssh_base "\$WINDEV_ALIAS" powershell "\${common_args[@]}" -Mode api_ask "\${force_args[@]}" -TaskBase64 "\$task_b64")"
    local api_b64
    api_b64="\$(printf '%s\n' "\$api_raw" | awk '/__WVIBE_B64_BEGIN__/{flag=1;next}/__WVIBE_B64_END__/{flag=0}flag' | tr -d '\r\n' | tr -cd 'A-Za-z0-9+/=')"
    if [ -n "\$api_b64" ]; then
      local decoded_text
      if decoded_text="\$(printf '%s' "\$api_b64" | base64 -d 2>/dev/null)"; then
        # Auto-fix common mojibake: choose representation with more Cyrillic chars.
        local pybin=""
        if command -v python3 >/dev/null 2>&1; then
          pybin="python3"
        elif command -v python >/dev/null 2>&1; then
          pybin="python"
        fi
        if [ -n "\$pybin" ]; then
          decoded_text="\$(printf '%s' "\$decoded_text" | "\$pybin" -c "import re,sys; s=sys.stdin.read(); \
def score(t): return len(re.findall(r'[Рђ-РЇР°-СЏРЃС‘]', t)); \
best=s; \
try: cand=s.encode('latin1', 'ignore').decode('utf-8', 'ignore'); \
except Exception: cand=s; \
best = cand if score(cand) > score(best) else best; \
print(best, end='')" 2>/dev/null || printf '%s' "\$decoded_text")"
        elif command -v iconv >/dev/null 2>&1; then
          local iconv_try
          iconv_try="\$(printf '%s' "\$decoded_text" | iconv -f ISO-8859-1 -t UTF-8 2>/dev/null || true)"
          if [ -n "\$iconv_try" ]; then
            decoded_text="\$iconv_try"
          fi
        fi
        printf '%s\n' "\$decoded_text"
      else
        echo "[warn] failed to decode api response, fallback to raw output."
        printf '%s\n' "\$api_raw"
      fi
    else
      printf '%s\n' "\$api_raw"
    fi
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

wtask() {
  if [ \$# -eq 0 ]; then
    echo "Usage: wtask <task text>"
    return 1
  fi
  wvibe api "\$*"
}

wtaskcli() {
  if [ \$# -eq 0 ]; then
    echo "Usage: wtaskcli <task text>"
    return 1
  fi
  wvibe ask --no-bootstrap "\$*"
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

_wmailbox_push_text() {
  local text_payload="\${1:-}"
  local src_tag="\${2:-termux}"
  if [ -z "\$text_payload" ]; then
    echo "[warn] empty text payload for mailbox inbox."
    return 1
  fi
  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 command not found in Termux"
    return 1
  fi
  local text_b64
  text_b64="\$(printf '%s' "\$text_payload" | base64 | tr -d '\r\n')"
  _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action inbox -Source '\$src_tag' -Text ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('\$text_b64')))"
}

wmailbox() {
  local action="\${1:-status}"
  shift || true
  case "\$action" in
    ensure|status|list|digest|show|prompt|handoff)
      _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action '\$action'"
      ;;
    inbox|push)
      local inbox_text=""
      if [ \$# -gt 0 ]; then
        inbox_text="\$*"
      else
        inbox_text="\$(cat)"
      fi
      _wmailbox_push_text "\$inbox_text" "termux"
      ;;
    pushlast)
      local last_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wrunbox_last.txt"
      if [ ! -f "\$last_file" ]; then
        echo "[warn] no last runbox output found: \$last_file"
        return 1
      fi
      _wmailbox_push_text "\$(cat "\$last_file")" "termux"
      ;;
    termux|pull)
      if ! _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null; then
        # Backward-compatible path if "termux" action is absent on remote script.
        _wps "Set-Location '\$WINDEV_PROJECT_WIN'; if (Test-Path '.\\\\ops\\\\mailbox\\\\for_termux.md') { Get-Content '.\\\\ops\\\\mailbox\\\\for_termux.md' -Raw -Encoding UTF8 } else { Write-Output '[warn] file not found: .\\\\ops\\\\mailbox\\\\for_termux.md' }"
      fi
      ;;
    pullclip)
      local reply
      local clip_mode="\${1:-body}"
      local clip_text=""
      local pull_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/for_termux_pullclip.md"
      if _wssh_base "\$WINDEV_ALIAS" "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(\$false); Get-Content -Raw -Encoding UTF8 '\$WINDEV_PROJECT_WIN\\\\ops\\\\mailbox\\\\for_termux.md'\"" > "\$pull_file" 2>/dev/null; then
        reply="\$(cat "\$pull_file" 2>/dev/null || true)"
      else
        echo "[warn] failed to fetch for_termux.md via ssh."
        return 1
      fi
      if [ -z "\$reply" ]; then
        echo "[warn] no termux reply found in mailbox."
        return 1
      fi
      case "\$clip_mode" in
        body)
          clip_text="\$(printf '%s' "\$reply" | awk 'f{print} /^Source:[[:space:]].*$/{f=1}' | sed '/./,\$!d')"
          if [ -z "\$clip_text" ]; then
            clip_text="\$reply"
          fi
          ;;
        full)
          clip_text="\$reply"
          ;;
        *)
          echo "Usage: wmailbox pullclip [body|full]"
          return 1
          ;;
      esac
      if command -v termux-clipboard-set >/dev/null 2>&1; then
        printf '%s' "\$clip_text" | termux-clipboard-set
        echo "[ok] Termux mailbox reply copied to Android clipboard (\$clip_mode)."
      else
        echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
      fi
      printf '%s\n' "\$clip_text"
      ;;
    reply)
      if [ \$# -eq 0 ]; then
        echo "Usage: wmailbox reply <text>"
        return 1
      fi
      if ! command -v base64 >/dev/null 2>&1; then
        echo "base64 command not found in Termux"
        return 1
      fi
      local reply_msg="\$*"
      local reply_b64
      reply_b64="\$(printf '%s' "\$reply_msg" | base64 | tr -d '\r\n')"
      _wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action reply -Source 'termux' -Text ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('\$reply_b64')))"
      ;;
    watch)
      local interval="\${1:-5}"
      case "\$interval" in
        ''|*[!0-9]*)
          echo "Usage: wmailbox watch [interval_seconds:int]"
          return 1
          ;;
      esac
      if [ "\$interval" -lt 1 ]; then
        interval=1
      fi
      echo "[watch] polling ops/mailbox/for_termux.md every \${interval}s (Ctrl+C to stop)"
      local last_sig=""
      local initialized=0
      while true; do
        local current_reply=""
        local is_valid=0
        if current_reply="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File '.\\\\scripts\\\\termux_ssh_toolkit\\\\windows\\\\10_mailbox.ps1' -ProjectPath '\$WINDEV_PROJECT_WIN' -Action termux" 2>/dev/null)"; then
          if [ -z "\$current_reply" ] || [[ "\$current_reply" == "[warn] file not found:"* ]]; then
            current_reply="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; if (Test-Path '.\\\\ops\\\\mailbox\\\\for_termux.md') { Get-Content '.\\\\ops\\\\mailbox\\\\for_termux.md' -Raw -Encoding UTF8 } else { '' }")"
          fi
        else
          current_reply="\$(_wps "Set-Location '\$WINDEV_PROJECT_WIN'; if (Test-Path '.\\\\ops\\\\mailbox\\\\for_termux.md') { Get-Content '.\\\\ops\\\\mailbox\\\\for_termux.md' -Raw -Encoding UTF8 } else { '' }")"
        fi
        if [[ "\$current_reply" == *"# Termux Mailbox"* ]]; then
          is_valid=1
        fi
        if [ "\$is_valid" -eq 0 ]; then
          local fallback_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/for_termux_watch.md"
          if _wssh_base "\$WINDEV_ALIAS" "powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \"Get-Content -Raw -Encoding UTF8 '\$WINDEV_PROJECT_WIN\\\\ops\\\\mailbox\\\\for_termux.md'\"" > "\$fallback_file" 2>/dev/null; then
            current_reply="\$(cat "\$fallback_file" 2>/dev/null || true)"
          fi
        fi
        local current_sig
        current_sig="\$(printf '%s' "\$current_reply" | cksum)"
        if [ "\$initialized" -eq 0 ]; then
          initialized=1
          last_sig="\$current_sig"
        elif [ "\$current_sig" != "\$last_sig" ]; then
          last_sig="\$current_sig"
          echo
          echo "----- [\$(date '+%Y-%m-%d %H:%M:%S')] mailbox update -----"
          printf '%s\n' "\$current_reply"
          if command -v termux-clipboard-set >/dev/null 2>&1; then
            printf '%s' "\$current_reply" | termux-clipboard-set
            echo "[watch] reply copied to Android clipboard."
          fi
          if command -v termux-notification >/dev/null 2>&1; then
            termux-notification --title "Mailbox update" --content "New reply in for_termux.md" >/dev/null 2>&1 || true
          fi
        fi
        sleep "\$interval"
      done
      ;;
    codexclip)
      local prompt
      local default_prompt
      default_prompt="Read ops/mailbox/for_codex.md and execute the tasks from it. If context is insufficient, ask up to 3 clarifying questions. In the answer: actions and changes first, then short risks and next step."
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
wplan "<С‡С‚Рѕ СЃРґРµР»Р°С‚СЊ>"
wmailbox codexclip
# Р·Р°С‚РµРј РѕС‚РєСЂРѕР№ Codex Рё РІСЃС‚Р°РІСЊ prompt РёР· Р±СѓС„РµСЂР°
FLOW
      ;;
    flowclip)
      local flow_text
      flow_text="wplan \"<what to do>\"
wmailbox codexclip
# then open Codex and paste the prompt from clipboard"
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
      echo "Usage: wmailbox [ensure|status|list|digest|show|termux|pull|pullclip|reply|watch|prompt|handoff|codexclip|flow|flowclip|resolve|inbox|push|pushlast]"
      return 1
      ;;
  esac
}

wrunbox() {
  if [ \$# -eq 0 ]; then
    echo "Usage: wrunbox <command>"
    return 1
  fi
  local cmd="\$*"
  local out_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wrunbox_last.txt"
  local ts
  ts="\$(date '+%Y-%m-%d %H:%M:%S')"

  echo "[runbox] \$cmd"
  { eval "\$cmd"; } > "\$out_file" 2>&1
  local rc=\$?
  cat "\$out_file"

  local cwd
  cwd="\$PWD"
  local report
  report="[runbox]
time: \$ts
cwd: \$cwd
command: \$cmd
exit_code: \$rc

output:
\$(cat "\$out_file")"
  _wmailbox_push_text "\$report" "termux-runbox" >/dev/null || true
  echo "[ok] run output pushed to ops/mailbox/inbox/LATEST.md"
  return \$rc
}

wring() {
  local cmd_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wring_cmd.sh"
  local out_file="\${TMPDIR:-/data/data/com.termux/files/usr/tmp}/wring_out.log"
  local run_rc=0

  if ! wmailbox termux > "\$cmd_file"; then
    echo "[error] failed to fetch command block from mailbox."
    return 1
  fi
  if [ ! -s "\$cmd_file" ]; then
    echo "[error] mailbox command block is empty."
    return 1
  fi

  bash "\$cmd_file" 2>&1 | tee "\$out_file"
  run_rc=\${PIPESTATUS[0]}

  if cat "\$out_file" | wmailbox inbox; then
    echo "[ok] wring output pushed to inbox."
  else
    echo "[error] failed to push wring output to inbox."
    return 70
  fi

  return "\$run_rc"
}

wclip() {
  if ! command -v termux-clipboard-set >/dev/null 2>&1; then
    echo "[warn] termux-clipboard-set not found. Install termux-api package/app."
    return 1
  fi
  local payload=""
  if [ \$# -gt 0 ]; then
    payload="\$*"
  else
    payload="\$(cat)"
  fi
  if [ -z "\$payload" ]; then
    echo "[warn] empty payload, nothing copied."
    return 1
  fi
  printf '%s' "\$payload" | termux-clipboard-set
  echo "[ok] copied to Android clipboard."
}

wpaste() {
  wmailbox pullclip "\$@"
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

wtutor() {
  local topic="\${1:-quick}"
  case "\$topic" in
    quick)
      cat <<'WTUTOR_QUICK'
РџСЂР°РєС‚РёРєР° (Р±С‹СЃС‚СЂС‹Р№ С†РёРєР»):
  1) wplan "РїСЂРѕРІРµСЂРєР° С†РёРєР»Р°"
  2) wmailbox codexclip
  3) РІСЃС‚Р°РІСЊ prompt РІ Codex
  4) wmailbox watch
  5) РєРѕРіРґР° РѕС‚РІРµС‚ РїРѕСЏРІРёС‚СЃСЏ -> РѕРЅ РЅР°РїРµС‡Р°С‚Р°РµС‚СЃСЏ Рё РїРѕРїР°РґРµС‚ РІ Р±СѓС„РµСЂ
WTUTOR_QUICK
      ;;
    mailbox)
      cat <<'WTUTOR_MAILBOX'
РџСЂР°РєС‚РёРєР° mailbox:
  1) wmailbox status
  2) wmailbox list
  3) wmailbox digest
  4) wmailbox show
  5) wmailbox reply "РўРµСЃС‚РѕРІС‹Р№ РѕС‚РІРµС‚ РґР»СЏ С‚РµР»РµС„РѕРЅР°"
  6) wmailbox pullclip

РћР¶РёРґР°РµРјРѕ:
  - reply РѕР±РЅРѕРІР»СЏРµС‚ ops/mailbox/for_termux.md
  - pullclip РїРµС‡Р°С‚Р°РµС‚ С‚РµРєСЃС‚ Рё РєРѕРїРёСЂСѓРµС‚ РµРіРѕ РІ Android clipboard
WTUTOR_MAILBOX
      ;;
    phone)
      cat <<'WTUTOR_PHONE'
РџСЂР°РєС‚РёРєР° phone-terminal:
  1) wphone init
  2) wphone run "echo PHONE_OK"
  3) wphone run "git status -sb"
  4) wphone capture 80

РћР¶РёРґР°РµРјРѕ:
  - capture РїРѕРєР°Р·С‹РІР°РµС‚ PHONE_OK
  - РЅРёР¶Рµ РІ capture РІРёРґРµРЅ РІС‹РІРѕРґ git status
WTUTOR_PHONE
      ;;
    duplex)
      cat <<'WTUTOR_DUPLEX'
РџСЂР°РєС‚РёРєР° duplex (2 СЃРµСЃСЃРёРё Termux):
  РЎРµСЃСЃРёСЏ A:
    wmailbox watch
  РЎРµСЃСЃРёСЏ B:
    wmailbox reply "РџСЂРёРІРµС‚ РёР· mailbox reply"

РћР¶РёРґР°РµРјРѕ РІ СЃРµСЃСЃРёРё A:
  - РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РІС‹РІРѕРґРёС‚СЃСЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё
  - С‚РµРєСЃС‚ РєРѕРїРёСЂСѓРµС‚СЃСЏ РІ Р±СѓС„РµСЂ (РµСЃР»Рё termux-api + Termux:API СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹)
WTUTOR_DUPLEX
      ;;
    *)
      echo "Usage: wtutor [quick|mailbox|phone|duplex]"
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
    _confirm "Р—Р°РїСѓСЃС‚РёС‚СЊ deploy-С†РёРєР»?" || return 1
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
  echo "Р¤Р°Р№Р» РЅР°Р±РѕСЂРѕРІ РєРѕРјР°РЅРґ РЅРµ РЅР°Р№РґРµРЅ: \$sets_file"
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

  echo "Р¤Р°Р№Р» СЃРїСЂР°РІРєРё РЅРµ РЅР°Р№РґРµРЅ: \$help_file"
}

wh() {
  whelp "\$@"
}
$BASH_BLOCK_END
__WINDEV_BASH_BLOCK__

echo
echo "Toolkit installed."
echo "Run: source ~/.bashrc"
echo "Run: whelp"

