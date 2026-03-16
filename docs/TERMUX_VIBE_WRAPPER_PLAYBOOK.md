# Termux + Windows SSH + Vibe Wrapper Playbook

This document is a transfer guide for the workflow:
`Termux -> SSH -> Windows -> wvibe`.

Goal: reproduce setup fast, with deterministic steps.

## 1) Copy These Files To A New Project

- `scripts/termux_ssh_toolkit/`
- `scripts/termux_ssh_toolkit/mcp/termux_bridge_mcp.py`
- `scripts/termux_ssh_toolkit/shared/whelp_ru.txt`
- `scripts/termux_ssh_toolkit/shared/whelp_sets_ru.txt`
- `.vibe/agents/phone-wrapper.toml`
- `VIBE.md`

## 2) Prerequisites

- Windows machine with OpenSSH Server enabled.
- Termux installed from F-Droid or GitHub release.
- Termux packages: `git`, `openssh`.
- Windows has `uv` and `mistral-vibe` installed.
- Project is available as a git repository on Windows.

## 3) One-Time Bootstrap

### Windows (PowerShell as Administrator)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\01_enable_openssh_server_admin.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\02_add_termux_pubkey.ps1 -PublicKeyPath .\local_setup\termux_ssh\secrets\termux_id_ed25519.pub
```

### Termux

```bash
apt update
pkg upgrade -y
pkg install git openssh -y
ssh-keygen -t ed25519 -C "termux-phone" -f ~/.ssh/id_ed25519
```

Add the public key to GitHub, then clone:

```bash
ssh -T git@github.com
git clone git@github.com:ivansvetlov/iikoinvoicebot.git
cd ~/iikoinvoicebot
```

Install toolkit aliases:

```bash
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 192.168.0.135 --termux-repo "$HOME/iikoinvoicebot" --skip-keygen
source ~/.bashrc
```

## 4) Daily Entry

From Termux:

```bash
wgo
```

What `wgo` does:
- local: enters your Termux repo path and runs `git pull --ff-only`;
- remote: opens interactive PowerShell in `%USERPROFILE%`.

Alternative starter alias:

```bash
wstartgo
```

If you want to only refresh local toolkit block first:

```bash
wrefresh
```

If you need project folder on Windows immediately:

```bash
wenter
```

## 5) Reliable Vibe Usage

From Termux:

```bash
wvibe doctor
wvibe ask --no-bootstrap "Reply exactly: OK"
wvshell
wplan "Пример задачи от телефона"
wmailbox codexclip
```

Inside `wvshell`:
- `/turns 12` to increase turn limit for long tasks
- `/mcp on` to allow MCP tools during ask requests
- `/mcpcmd <exact command>` for direct MCP command run

Mailbox flow:
1. Add task from phone: `wplan "..."`
2. Build ready prompt + copy to Android clipboard: `wmailbox codexclip`
3. Open Codex chat and paste clipboard text
4. Optional: `wmailbox flowclip` to copy the full command pack
5. Pull answer to phone: `wmailbox pull` (or `wmailbox pullclip`)
6. Auto-track new answers: `wmailbox watch`

Phone terminal control (local tmux in Termux):
1. `wphone init`
2. `wphone run "git status -sb"`
3. `wphone capture 80`
4. `wphone attach` (optional)

Practical next plan:
1. Stabilize `wplan -> wmailbox codexclip -> paste`.
2. Use `wphone run/capture` for repeated dev commands from phone.
3. Add one-command answer pull from mailbox to phone.
   Status: implemented via `wmailbox pull` / `wmailbox pullclip`.
4. Promote stable presets into day-to-day wrappers.

Inside Windows shell (`MiBookPro`), install wrappers once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\07_install_windows_wvibe_aliases.ps1
```

Verify:

```powershell
where.exe wvibe
where.exe whelp
whelp
wvibe doctor
```

Available commands after install:
- `whelp`, `wstatus`, `wpull`, `wstart`, `wstop`, `wrestart`, `wtail`, `wtest`, `wdeploy`, `wrun`
- `wvibe ...`
- `wreconnect`
- `wmcp "<exact command>"`

## 6) Hard Rules To Avoid Quoting Failures

1. One command per line.
2. For `wcmd`, wrap the full PowerShell command in single quotes.
3. Use exact path: `C:\Users\MiBookPro\.local\bin`.
4. After Termux reinstall, re-add phone pubkey on Windows.
5. If a command hangs, first validate transport with `wcmd "Get-Date"`.

Good:

```bash
wcmd '$env:Path="C:\Users\MiBookPro\.local\bin;" + $env:Path; vibe --version'
```

Bad:

```bash
wcmd "$env:Path=..."
```

## 7) Quick Diagnostics

1. Check SSH:
```bash
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes MiBookPro@192.168.0.135
```
2. Check alias load:
```bash
type wvibe
```
3. Check wrapper health:
```bash
wvibe doctor
```
4. If `wvibe` is not found in Windows:
```powershell
echo $env:Path
where.exe wvibe
```

## 8) Scaling Recommendation

Keep the same toolkit layout (`scripts/termux_ssh_toolkit`) in each new project.
This makes setup repeatable and removes manual guesswork.
