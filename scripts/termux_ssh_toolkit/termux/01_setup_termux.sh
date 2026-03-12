#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if ! command -v pkg >/dev/null 2>&1; then
  echo "This script must be run in Termux (pkg command not found)."
  exit 1
fi

echo "[1/4] Update packages..."
pkg update -y >/dev/null

echo "[2/4] Install OpenSSH client..."
pkg install -y openssh >/dev/null

echo "[3/4] Ensure ~/.ssh exists..."
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  echo "[4/4] Generating SSH key..."
  ssh-keygen -t ed25519 -C "termux-phone" -f "$HOME/.ssh/id_ed25519" -N ""
else
  echo "[4/4] SSH key already exists."
fi

chmod 600 "$HOME/.ssh/id_ed25519"
chmod 644 "$HOME/.ssh/id_ed25519.pub"

echo
echo "Public key:"
cat "$HOME/.ssh/id_ed25519.pub"
echo
echo "Copy this key to Windows and add it with:"
echo "powershell -ExecutionPolicy Bypass -File .\\scripts\\termux_ssh_toolkit\\windows\\02_add_termux_pubkey.ps1 -PublicKeyPath .\\termux_id_ed25519.pub"
