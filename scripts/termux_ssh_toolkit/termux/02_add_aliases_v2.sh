#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Atomic toolkit installation script (v2)
# This script:
# 1. Creates ~/.config/windev/ directory
# 2. Generates toolkit.sh by substituting variables into template
# 3. Validates syntax with bash -n
# 4. Atomically moves into place
# 5. Updates ~/.bashrc with minimal bootstrap
# 6. Handles idempotency (safe to rerun)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

WIN_USER="${1:-MiBookPro}"
WIN_HOST="${2:-192.168.0.135}"
HOST_ALIAS="${3:-windev}"
WIN_PROJECT="${4:-C:\Users\MiBookPro\PycharmProjects\PythonProject}"
WIN_UV_BIN="${5:-C:\Users\MiBookPro\.local\bin}"
TERMUX_REPO="${6:-$HOME/iikoinvoicebot}"

SSH_DIR="$HOME/.ssh"
SSH_CONFIG="$SSH_DIR/config"
BASHRC="$HOME/.bashrc"
WINDEV_CONFIG_DIR="$HOME/.config/windev"
TOOLKIT_FILE="$WINDEV_CONFIG_DIR/toolkit.sh"
TOOLKIT_TEMPLATE="$SCRIPT_DIR/../shared/toolkit_functions.sh"
VERSION_FILE="$WINDEV_CONFIG_DIR/.version"
INSTALL_DATE="$(date -u '+%Y-%m-%d_%H%M%S')"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log_info() {
  echo "[info] $*"
}

log_warn() {
  echo "[warn] $*" >&2
}

log_error() {
  echo "[error] $*" >&2
}

die() {
  log_error "$*"
  exit 1
}

sed_escape_replacement() {
  # Escape replacement text for sed s||| to preserve Windows backslashes and '&'.
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

# ============================================================================
# SSH CONFIG SETUP
# ============================================================================

setup_ssh_config() {
  log_info "Setting up SSH config for $HOST_ALIAS -> $WIN_HOST"
  
  mkdir -p "$SSH_DIR"
  chmod 700 "$SSH_DIR"
  [ -f "$SSH_CONFIG" ] || touch "$SSH_CONFIG"

  # Remove old block if it exists (idempotency)
  local tmp
  tmp="$(mktemp)"
  local ssh_block_begin="# >>> ${HOST_ALIAS}-ssh-host >>>"
  local ssh_block_end="# <<< ${HOST_ALIAS}-ssh-host <<<"
  
  awk -v b="$ssh_block_begin" -v e="$ssh_block_end" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$SSH_CONFIG" > "$tmp"
  mv "$tmp" "$SSH_CONFIG"

  # Append new block
  cat >> "$SSH_CONFIG" <<EOF
$ssh_block_begin
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
$ssh_block_end
EOF

  log_info "SSH config updated"
}

# ============================================================================
# TOOLKIT INSTALLATION (ATOMIC)
# ============================================================================

install_toolkit_atomically() {
  log_info "Generating toolkit.sh from template"
  
  # Verify template exists
  if [ ! -f "$TOOLKIT_TEMPLATE" ]; then
    die "Template not found: $TOOLKIT_TEMPLATE"
  fi

  # Create config dir
  mkdir -p "$WINDEV_CONFIG_DIR"
  chmod 700 "$WINDEV_CONFIG_DIR"

  # Generate toolkit into temp file with variable substitution
  local temp_toolkit
  temp_toolkit="$(mktemp)"
  local host_alias_esc
  local win_user_esc
  local win_host_esc
  local win_project_esc
  local win_uv_bin_esc
  local termux_repo_esc

  host_alias_esc="$(sed_escape_replacement "$HOST_ALIAS")"
  win_user_esc="$(sed_escape_replacement "$WIN_USER")"
  win_host_esc="$(sed_escape_replacement "$WIN_HOST")"
  win_project_esc="$(sed_escape_replacement "$WIN_PROJECT")"
  win_uv_bin_esc="$(sed_escape_replacement "$WIN_UV_BIN")"
  termux_repo_esc="$(sed_escape_replacement "$TERMUX_REPO")"

  if ! sed \
    -e "s|{{HOST_ALIAS}}|$host_alias_esc|g" \
    -e "s|{{WIN_USER}}|$win_user_esc|g" \
    -e "s|{{WIN_HOST}}|$win_host_esc|g" \
    -e "s|{{WIN_PROJECT}}|$win_project_esc|g" \
    -e "s|{{WIN_UV_BIN}}|$win_uv_bin_esc|g" \
    -e "s|{{TERMUX_REPO}}|$termux_repo_esc|g" \
    "$TOOLKIT_TEMPLATE" > "$temp_toolkit"; then
    rm -f "$temp_toolkit"
    die "Failed to generate toolkit"
  fi

  # Validate syntax
  log_info "Validating toolkit syntax (bash -n)"
  if ! bash -n "$temp_toolkit"; then
    rm -f "$temp_toolkit"
    die "Toolkit syntax validation failed"
  fi

  # Backup existing toolkit (if any)
  if [ -f "$TOOLKIT_FILE" ]; then
    log_info "Backing up existing toolkit to toolkit.sh.bak"
    cp "$TOOLKIT_FILE" "$TOOLKIT_FILE.bak"
  fi

  # Atomic move
  mv "$temp_toolkit" "$TOOLKIT_FILE"
  chmod 600 "$TOOLKIT_FILE"

  log_info "Toolkit installed to $TOOLKIT_FILE"
}

# ============================================================================
# BASHRC BOOTSTRAP SETUP
# ============================================================================

setup_bashrc_bootstrap() {
  log_info "Setting up minimal ~/.bashrc bootstrap"

  # Backup ~/.bashrc (if it has the old toolkits)
  if grep -q ">>> ${HOST_ALIAS}-dev-toolkit >>>" "$BASHRC" 2>/dev/null || \
     grep -q "TOOLKIT_PATH" "$BASHRC" 2>/dev/null; then
    if [ ! -f "$BASHRC.bak" ]; then
      log_info "Backing up ~/.bashrc to ~/.bashrc.bak"
      cp "$BASHRC" "$BASHRC.bak"
    fi
  fi

  # Remove old monolithic toolkit block (if exists)
  if grep -q ">>> ${HOST_ALIAS}-dev-toolkit >>>" "$BASHRC" 2>/dev/null; then
    log_info "Removing old monolithic toolkit block from ~/.bashrc"
    local tmp
    tmp="$(mktemp)"
    local bash_block_begin="# >>> ${HOST_ALIAS}-dev-toolkit >>>"
    local bash_block_end="# <<< ${HOST_ALIAS}-dev-toolkit <<<"
    
    awk -v b="$bash_block_begin" -v e="$bash_block_end" '
      $0==b {skip=1; next}
      $0==e {skip=0; next}
      !skip {print}
    ' "$BASHRC" > "$tmp"
    mv "$tmp" "$BASHRC"
  fi

  # Add bootstrap if not present
  if ! grep -q "TOOLKIT_PATH" "$BASHRC" 2>/dev/null; then
    log_info "Adding toolkit bootstrap to ~/.bashrc"
    cat >> "$BASHRC" <<'BOOTSTRAP'

# Minimal bootstrap for windev toolkit (added by install.sh)
TOOLKIT_PATH="${HOME}/.config/windev/toolkit.sh"
if [ -f "$TOOLKIT_PATH" ]; then
  source "$TOOLKIT_PATH"
else
  echo "[warn] Toolkit not found at $TOOLKIT_PATH" >&2
  echo "[info] Run: bash scripts/termux_ssh_toolkit/termux/install.sh --win-host <ip>" >&2
fi
BOOTSTRAP
  else
    log_info "Toolkit bootstrap already present in ~/.bashrc"
  fi
}

# ============================================================================
# VERSION TRACKING
# ============================================================================

record_version() {
  log_info "Recording installation version"
  cat > "$VERSION_FILE" <<EOF
version: 2026-03-18_v2
installed: $INSTALL_DATE
host_alias: $HOST_ALIAS
win_host: $WIN_HOST
win_user: $WIN_USER
template: $TOOLKIT_TEMPLATE
EOF
  chmod 600 "$VERSION_FILE"
}

# ============================================================================
# VALIDATION
# ============================================================================

validate_installation() {
  log_info "Validating installation"

  # Check syntax
  if ! bash -n "$BASHRC"; then
    die "~/.bashrc syntax validation failed"
  fi

  # Check toolkit exists
  if [ ! -f "$TOOLKIT_FILE" ]; then
    die "Toolkit file not found: $TOOLKIT_FILE"
  fi

  # Dry-run source to catch runtime errors
  if ! bash -c "source '$TOOLKIT_FILE' 2>/dev/null && command -v wmailbox >/dev/null"; then
    die "Toolkit doesn't define wmailbox function"
  fi

  log_info "Installation validation passed"
}

# ============================================================================
# MAIN INSTALLATION FLOW
# ============================================================================

main() {
  log_info "=== Toolkit Installation (v2 - Atomic) ==="
  log_info "Host alias: $HOST_ALIAS"
  log_info "Windows host: $WIN_HOST"
  log_info "Windows user: $WIN_USER"
  log_info "Termux repo: $TERMUX_REPO"
  echo

  setup_ssh_config
  echo

  install_toolkit_atomically
  echo

  setup_bashrc_bootstrap
  echo

  record_version
  echo

  validate_installation
  echo

  log_info "=== Installation Complete ==="
  echo "Next steps:"
  echo "  1) source ~/.bashrc"
  echo "  2) whelp"
  echo "  3) wstatus (test SSH connection)"
}

main "$@"
