# Termux Mailbox Stable Workflow (2026-03-16)

This document fixes the current operational baseline for phone workflow.

## Scope

- Phone: Termux + Termux:API
- Host: Windows (`windev`) via SSH
- Mailbox channel: `ops/mailbox/for_termux.md`
- Clipboard-first usage for command packs

## Current Working Commands

- `wmailbox reply "<text>"`  
  Write reply text into `for_termux.md`.

- `wpaste`  
  Pull mailbox reply and copy to Android clipboard (default `body` mode).

- `wpaste full`  
  Pull full mailbox document with header/meta.

- `wclip "<one-line command>"`  
  Copy a single command to clipboard.

- `cat <<'EOF' | wclip ... EOF`  
  Copy a multi-line command block to clipboard.

## Session Rule (locked)

- Agent sends command groups as ready-to-paste blocks.
- User pulls block with `wpaste` and pastes into Termux.
- Blocks for execution contain commands only (no explanations in the block).
- Strict policy: executable command blocks are delivered only via mailbox; chat messages contain status/explanations/results only.

## Recovery Commands

If host key/IP/session changed:

```bash
wsetip 100.72.204.121
ssh -o ConnectTimeout=5 -o ConnectionAttempts=1 windev "echo ok"
```

Refresh toolkit after pull:

```bash
cd ~/iikoinvoicebot
git pull --ff-only
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 100.72.204.121 --termux-repo "$HOME/iikoinvoicebot" --skip-keygen
source ~/.bashrc
```

Clipboard smoke check:

```bash
termux-clipboard-set "X1"
termux-clipboard-get
```

## Known Good Path for Mailbox -> Clipboard

Validated as stable after fixes:

1. `wmailbox reply "OK"`
2. `wpaste`
3. `termux-clipboard-get` returns `OK`

## Notes on Previous Failures

- `failed to fetch for_termux.md via ssh`: usually SSH session/interactivity/host-key mismatch; fixed by non-interactive SSH options and reconnect.
- Clipboard looked copied but was empty: upstream command stream was empty or metadata-only, not a clipboard API failure.
- Mojibake in terminal: output encoding/noisy remote stream; operational workaround is ASCII command blocks + clipboard-first flow.

## Branch / Commits (workflow hardening)

- Added `wclip` helper (copy text/blocks to clipboard).
- Added `wpaste` alias (`wmailbox pullclip`).
- Hardened `pullclip` path to direct SSH fetch of `for_termux.md`.
- SSH wrapper updated for non-interactive behavior (`BatchMode`, `NumberOfPasswordPrompts=0`, `StrictHostKeyChecking=accept-new`).
