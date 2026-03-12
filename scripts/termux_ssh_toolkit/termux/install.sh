#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

WIN_USER="MiBookPro"
WIN_HOST=""
HOST_ALIAS="windev"
WIN_PROJECT=""
WIN_UV_BIN=""
TERMUX_REPO="$HOME/iikoinvoicebot"
SKIP_KEYGEN=0

if ! command -v pkg >/dev/null 2>&1; then
  echo "This installer must be run in Termux."
  exit 1
fi

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/termux_ssh_toolkit/termux/install.sh [options]

Options:
  --win-user <name>      Windows user (default: MiBookPro)
  --win-host <ip>        Windows LAN IP (required)
  --alias <name>         SSH alias in ~/.ssh/config (default: windev)
  --project <path>       Windows project path (default: C:\Users\<user>\PycharmProjects\PythonProject)
  --uv-bin <path>        Windows uv bin path (default: C:\Users\<user>\.local\bin)
  --termux-repo <path>   Local Termux repo path for one-command resume (default: ~/iikoinvoicebot)
  --skip-keygen          Skip SSH key setup in Termux
  -h, --help             Show this help
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --win-user)
      WIN_USER="${2:-}"
      shift 2
      ;;
    --win-host)
      WIN_HOST="${2:-}"
      shift 2
      ;;
    --alias)
      HOST_ALIAS="${2:-}"
      shift 2
      ;;
    --project)
      WIN_PROJECT="${2:-}"
      shift 2
      ;;
    --uv-bin)
      WIN_UV_BIN="${2:-}"
      shift 2
      ;;
    --termux-repo)
      TERMUX_REPO="${2:-}"
      shift 2
      ;;
    --skip-keygen)
      SKIP_KEYGEN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [ -z "$WIN_HOST" ]; then
  echo "Error: --win-host is required"
  usage
  exit 1
fi

if [ -z "$WIN_PROJECT" ]; then
  WIN_PROJECT="C:\\Users\\$WIN_USER\\PycharmProjects\\PythonProject"
fi
if [ -z "$WIN_UV_BIN" ]; then
  WIN_UV_BIN="C:\\Users\\$WIN_USER\\.local\\bin"
fi

if [ "$SKIP_KEYGEN" -eq 0 ]; then
  bash "$SCRIPT_DIR/01_setup_termux.sh"
fi

bash "$SCRIPT_DIR/02_add_aliases.sh" "$WIN_USER" "$WIN_HOST" "$HOST_ALIAS" "$WIN_PROJECT" "$WIN_UV_BIN" "$TERMUX_REPO"

echo
echo "Done."
echo "Next:"
echo "  source ~/.bashrc"
echo "  whelp"
