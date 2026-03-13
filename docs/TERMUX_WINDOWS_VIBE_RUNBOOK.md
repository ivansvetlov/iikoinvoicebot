# Termux -> Windows -> Vibe Runbook (No Guesswork)

This is a strict setup and recovery route based on real failures from long troubleshooting.
Use this when you want predictable results and fast recovery.

## 0) Critical Rules

1. Run one command per line.
2. In `wcmd`, wrap PowerShell in single quotes:
   - good: `wcmd '$env:Path="..."; vibe --version'`
   - bad: `wcmd "$env:Path=..."`
3. Use exact path: `C:\Users\MiBookPro\.local\bin`
4. After Termux reinstall, re-add the new phone SSH key on Windows.
5. For phone workflow, prefer `wvibe ask ...` over interactive `wvibe` if TTY is unstable.

## 1) Windows One-Time Setup

Open PowerShell as Administrator in project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\01_enable_openssh_server_admin.ps1
Restart-Service sshd
Get-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
```

Expected:
- `sshd` is `Running`
- port `22` is in `Listen`

## 2) Termux One-Time Setup

Use modern Termux (F-Droid or GitHub release).

```bash
apt update
pkg upgrade -y
pkg install git openssh -y
ssh-keygen -t ed25519 -C "termux-phone" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Add pubkey to GitHub:
- GitHub -> Settings -> SSH and GPG keys -> New SSH key

Clone project:

```bash
ssh -T git@github.com
git clone git@github.com:ivansvetlov/iikoinvoicebot.git
cd ~/iikoinvoicebot
git checkout feature/infra-termux-vibe-mcp
```

## 3) Re-Add Phone Key on Windows (Required After Termux Reinstall)

1. Copy output of `cat ~/.ssh/id_ed25519.pub`.
2. Save to `.\local_setup\termux_ssh\secrets\termux_id_ed25519.pub` on Windows.
3. Run:

```powershell
.\scripts\termux_ssh_toolkit\windows\02_add_termux_pubkey.ps1 -PublicKeyPath .\local_setup\termux_ssh\secrets\termux_id_ed25519.pub
Restart-Service sshd
```

## 4) Install Toolkit Aliases in Termux

```bash
cd ~/iikoinvoicebot
git pull
bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 192.168.0.135 --termux-repo "$HOME/iikoinvoicebot" --skip-keygen
source ~/.bashrc
```

Sanity check:

```bash
wcmd "Get-Date"
```

One-command resume from fresh Termux session:

```bash
wgo
```

`wgo` now does local prep before SSH:
- enters configured Termux repo (`$WINDEV_TERMUX_REPO`)
- runs `git pull --ff-only`
- returns to original local folder
- opens interactive PowerShell in Windows `%USERPROFILE%`

Optional starter alias (same behavior):

```bash
wstartgo
```

Force-refresh aliases + config before SSH:

```bash
wrefresh
```

If you need to land directly in the Windows project folder, use:

```bash
wenter
```

`wenter` opens interactive PowerShell with project folder as current location.

What it does:
- local: `cd $WINDEV_TERMUX_REPO` (if exists)
- remote: opens interactive PowerShell and enters `%USERPROFILE%` (`C:\Users\MiBookPro`)
- colorized command input comes from `PSReadLine` in this PowerShell session

## 4.1) Install `wvibe` Command Inside Windows Shell

This installs full `w*` toolkit commands in Windows shell (`whelp`, `wstatus`, `wtest`, `wdeploy`, `wvibe`, etc.).
Use this if you want the same command style directly inside `MiBookPro`.

Run once on Windows in project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\07_install_windows_wvibe_aliases.ps1
```

Then verify inside Windows shell:

```powershell
where.exe wvibe
where.exe whelp
whelp
wvibe doctor
```

If `wvibe` is still not found:
1. Close and reopen SSH session.
2. Ensure `%USERPROFILE%\.local\bin` is in `PATH`:
```powershell
echo $env:Path
```

## 5) Stable Vibe Usage from Phone

```bash
wvibe doctor
wvibe ask --no-bootstrap "Reply exactly: OK"
wvshell
wplan "Проверить TODO и обновить статус Stage 8"
wmailbox digest
wvibe ask "read docs/START_HERE_NEW_CHAT.md and return short project status"
```

For longer requests in `wvshell`:
- `/turns 12` to raise ask turn limit
- `/mcp on` to keep MCP tools enabled for asks
- `/mcpcmd <exact command>` for exact host command execution via MCP

Mailbox handoff:
1. `wplan "<task from phone>"`
2. `wmailbox digest`
3. In Vibe ask: read `ops/mailbox/for_codex.md` and prepare concise request for Codex.
4. Send Codex: `read ops/mailbox/for_codex.md`

## 6) Direct Bypass Test (No Aliases)

If wrapper/alias behavior is suspicious, run this exact command from Termux:

```bash
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes MiBookPro@192.168.0.135 'powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\Users\MiBookPro\PycharmProjects\PythonProject\scripts\termux_ssh_toolkit\windows\06_run_vibe_wrapper.ps1" -ProjectPath "C:\Users\MiBookPro\PycharmProjects\PythonProject" -UvBinPath "C:\Users\MiBookPro\.local\bin" -Mode ask -SkipBootstrap -TaskBase64 "UmVwbHkgZXhhY3RseTogT0s="'
```

Expected output:
- `OK`

## 7) Symptom -> Cause -> Exact Fix

### A) `Unable to locate package openssh`
Cause:
- broken or old Termux package source.

Fix:
```bash
apt update
pkg upgrade -y
pkg install git openssh -y
```
If still broken, reinstall Termux from F-Droid/GitHub release.

### B) `Permission denied (publickey,password,keyboard-interactive)` when connecting to Windows
Cause:
- phone key missing in Windows `authorized_keys`.

Fix:
- run section 3.

### C) `vibe.exe not found at C:\Users\MiBookPro.local\bin\vibe.exe`
Cause:
- path typo (`.local` missing backslash).

Fix:
- use `C:\Users\MiBookPro\.local\bin`.

### D) `:Path` or broken PowerShell parsing in `wcmd`
Cause:
- used double quotes around `wcmd "..."`, so Bash expanded `$env`.

Fix:
- always use single quotes around whole PowerShell command:
```bash
wcmd '$env:Path="C:\Users\MiBookPro\.local\bin;" + $env:Path; vibe --version'
```

### E) `wvibe ask` hangs while `wcmd "Get-Date"` works
Cause:
- shell composition issue or unstable terminal chain.

Fix:
1. `git pull`
2. reinstall aliases:
   - `bash scripts/termux_ssh_toolkit/termux/install.sh --win-user MiBookPro --win-host 192.168.0.135 --termux-repo "$HOME/iikoinvoicebot" --skip-keygen`
3. `source ~/.bashrc`
4. on Windows run:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\termux_ssh_toolkit\windows\07_install_windows_wvibe_aliases.ps1`
5. run section 6 direct bypass test.

### F) SSH timeout to host
Cause:
- IP changed or `sshd` state issue.

Fix on Termux:
```bash
wsetip 192.168.0.135
nc -z -w 3 192.168.0.135 22
```

Fix on Windows:
```powershell
Restart-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
ipconfig
```

## 8) Daily Fast Path

```bash
wgo
wcmd "Get-Date"
wvibe doctor
wvibe ask "what is TODO status?"
```

If one command fails, use section 7 and apply only the exact matching fix.
