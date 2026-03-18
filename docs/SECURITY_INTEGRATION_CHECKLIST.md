# SECURITY & INTEGRATION: Checklist, Risk Analysis, Post-Install Validation

## 1. SMOKE-CHECK AFTER INSTALLATION

### Минимальный набор проверок

```bash
# Run immediately after: source ~/.bashrc

# 1.1 Синтаксис
bash -n ~/.bashrc                           # ✓ Should pass
bash -n ~/.config/windev/toolkit.sh         # ✓ Should pass

# 1.2 Функции доступны
command -v wmailbox                         # ✓ Must exist
command -v whelp                            # ✓ Must exist
command -v wstatus                          # ✓ Must exist
command -v wrunbox                          # ✓ Must exist
command -v wring                            # ✓ Must exist
command -v wpaste                           # ✓ Must exist
command -v wvibe                            # ✓ Must exist

# 1.3 whelp работает полностью
whelp | wc -l                               # Should output >50
whelp | head -20                            # Visual check: Russian text readable
whelp sets | wc -l                          # Should output >10

# 1.4 Нет неожиданного вывода при source
OUTPUT=$(bash -c "source ~/.bashrc 2>&1")
[ -z "$OUTPUT" ] && echo "OK" || echo "FAIL: $OUTPUT"

# 1.5 SSH конфиг есть
ls -la ~/.ssh/config                        # Should exist
grep "^Host windev" ~/.ssh/config           # Should find entry
```

### Автоматизированный smoke-check (script)

```bash
# Запустить скрипт
bash scripts/termux_ssh_toolkit/termux/smoke_check.sh

# Должен вывести все ✓ checks, без ✗
```

---

## 2. E2E VALIDATION: WRING FULL CYCLE

### Сценарий: fetch → execute → push → verify

```bash
# Prerequisites:
# 1. SSH работает: wstatus (успешно выполнится)
# 2. Mailbox accessible: wmailbox status (покажет счётчики)

# Step 1: Create test command in mailbox
wmailbox reply "echo 'Test from wring' && date"

# Step 2: Execute wring
wring
# Expected output:
# [wring] executing command...
# Test from wring
# <timestamp>
# [wring] pushing result to mailbox...
# [wring-result] run_rc=0 push_status=ok inbox=ops/mailbox/inbox
# [ok] wring: command succeeded, result pushed to mailbox

# Step 3: Verify result in mailbox (on host)
wmailbox termux
# Should show the wring output

# Step 4: Check exit code
wring && echo "Exit code: 0 (success)"
```

### Сценарий: error handling

```bash
# Test 1: Empty mailbox
wmailbox reply ""
wring
# Expected: [error] wring: command block is empty, return 1

# Test 2: Command with error
wmailbox reply "false"
wring
# Expected: [warn] wring: command exited with code 1, push_status=ok, return 1

# Test 3: SSH unavailable (simulate)
wsetip 192.0.2.1  # Non-routable IP (will timeout)
wring
# Expected: [error] wring: failed to fetch command from mailbox, return 1
wsetip 192.168.1.100  # Restore original
```

---

## 3. MAILBOX WORKFLOW E2E

### Полный цикл: телефон → команда → хост → результат

```bash
# Terminal 1: Operator (on host, Windows PC)
# Sets up command for Termux:
# (Using mailbox script or manual edit of ops/mailbox/for_termux.md)
echo "git status" | wmailbox reply

# Terminal 2: Termux (on phone)
# Step 1: Pull command
wpaste
# Expected: Shows "git status" command in clipboard

# Step 2: Execute
wring
# Executes command, pushes result to mailbox

# Step 3: Back to host, verify result
wmailbox termux | tail -20
# Should show git status output
```

---

## 4. RISKS & MITIGATIONS

### Risk 1: Corrupted ~/.bashrc during install

**Scenario:** Installation fails mid-way, ~/.bashrc left in broken state

**Mitigation:**
- ✓ `02_add_aliases_v2.sh` creates `~/.bashrc.bak` before modifications
- ✓ Old block is removed atomically with `awk`
- ✓ New bootstrap added only if not present
- ✓ Syntax validation before install (`bash -n`)

**Recovery:**
```bash
# If ~/.bashrc is broken:
cp ~/.bashrc.bak ~/.bashrc
source ~/.bashrc
# Or reinstall:
bash scripts/termux_ssh_toolkit/termux/install.sh --win-host 192.168.1.100 --skip-keygen
```

---

### Risk 2: Broken toolkit.sh prevents shell from loading

**Scenario:** Syntax error in toolkit.sh, no functions available

**Mitigation:**
- ✓ toolkit.sh is validated with `bash -n` before installation
- ✓ Backup created: `toolkit.sh.bak`
- ✓ Bootstrap in ~/.bashrc warns if toolkit not found (doesn't crash)

**Recovery:**
```bash
# If toolkit.sh is broken:
cp ~/.config/windev/toolkit.sh.bak ~/.config/windev/toolkit.sh
source ~/.bashrc
# Or reinstall:
bash scripts/termux_ssh_toolkit/termux/install.sh --win-host 192.168.1.100 --skip-keygen
```

---

### Risk 3: SSH keys missing or permissions wrong

**Scenario:** SSH operations fail (no key, wrong permissions)

**Mitigation:**
- ✓ `01_setup_termux.sh` creates/fixes SSH keys during install
- ✓ `wfixssh` command available to repair permissions
- ✓ SSH config uses `IdentitiesOnly yes` to prevent auth fallback

**Recovery:**
```bash
# Fix SSH permissions:
wfixssh

# Or manually:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub

# Test:
wssh "echo OK"
```

---

### Risk 4: Encoding issues (mojibake) in output

**Scenario:** Russian text in whelp or mailbox output is garbled

**Mitigation:**
- ✓ All .sh files are UTF-8 (no BOM)
- ✓ Line endings are LF (Unix standard)
- ✓ `_wps()` functions use base64 transport to avoid encoding issues
- ✓ PowerShell prelude sets `[Console]::OutputEncoding` to UTF-8

**Recovery:**
```bash
# Check encoding:
file -i ~/.config/windev/toolkit.sh  # Should be utf-8
file -i scripts/termux_ssh_toolkit/shared/whelp_ru.txt  # Should be utf-8

# If wrong: fix before using
# (See ENCODING_MOJIBAKE_FIX.md)

# Verify Russian text works:
whelp | grep -E '[а-яА-ЯЁё]'  # Should find Russian characters
```

---

### Risk 5: wring returns wrong exit code, script depends on it

**Scenario:** `wring "command"` returns 0 even though command failed

**Mitigation:**
- ✓ Improved wring (see WRING_RETURN_CODE_SEMANTICS.md):
  - Returns command's exit code (run_rc)
  - Pushes explicit `[wring-result]` line with both statuses
  - Clear [ok]/[warn]/[error] messages
  - Operator can parse both command AND push status

**Recovery:**
```bash
# Parse wring result:
OUTPUT=$(wring "git status" 2>&1)
RESULT=$(echo "$OUTPUT" | grep "^\[wring-result\]")
echo "Result: $RESULT"
# [wring-result] run_rc=0 push_status=ok inbox=ops/mailbox/inbox

# Check both statuses:
RUN_RC=$(echo "$RESULT" | grep -oP 'run_rc=\K\d+')
PUSH_STATUS=$(echo "$RESULT" | grep -oP 'push_status=\K\w+')

if [ "$PUSH_STATUS" != "ok" ]; then
  echo "WARNING: Data was not pushed to mailbox!"
fi
```

---

### Risk 6: wmailbox SSH timeout/failure

**Scenario:** SSH to Windows host fails, wmailbox operations timeout

**Mitigation:**
- ✓ SSH config has `ConnectTimeout 5, ConnectionAttempts 1` (fail fast)
- ✓ Non-interactive options: `BatchMode yes`, `StrictHostKeyChecking accept-new`
- ✓ `wsetip` command available to update host IP
- ✓ Error messages from wmailbox are explicit

**Recovery:**
```bash
# Update IP if changed:
wsetip 192.168.1.101

# Test SSH connectivity:
wssh "echo OK"

# If still fails, check:
cat ~/.ssh/config | grep -A 10 "^Host windev"
ls -la ~/.ssh/id_ed25519

# Verify host is reachable:
ncat 192.168.1.101 22  # Should connect to SSH port
```

---

### Risk 7: /tmp or TMPDIR full, temp files can't be created

**Scenario:** wring can't create temp files for command/output

**Mitigation:**
- ✓ toolkit.sh uses `${TMPDIR:-/tmp}` (respects TMPDIR env var)
- ✓ Termux has `/data/data/com.termux/files/usr/tmp` (usually has space)
- ✓ Error handling in wring checks for empty files

**Recovery:**
```bash
# Check disk space:
df -h $TMPDIR

# If full, clean up:
rm -f /tmp/wring_* /tmp/for_termux_* 2>/dev/null

# Or use different TMPDIR:
export TMPDIR=/data/data/com.termux/files/usr/tmp
wring "command"
```

---

## 5. PRE-DEPLOYMENT CHECKLIST

Before deploying to production (before commit):

- [ ] All .sh files are UTF-8 (no BOM)
  ```bash
  file -i scripts/termux_ssh_toolkit/**/*.sh | grep utf-8
  ```

- [ ] All files have LF line endings
  ```bash
  file scripts/termux_ssh_toolkit/**/*.sh | grep -v CRLF
  ```

- [ ] toolkit_functions.sh syntax is valid
  ```bash
  bash -n scripts/termux_ssh_toolkit/shared/toolkit_functions.sh
  ```

- [ ] 02_add_aliases_v2.sh syntax is valid
  ```bash
  bash -n scripts/termux_ssh_toolkit/termux/02_add_aliases_v2.sh
  ```

- [ ] Updated install.sh has correct shebang
  ```bash
  head -1 scripts/termux_ssh_toolkit/termux/install.sh
  # Should be: #!/data/data/com.termux/files/usr/bin/bash
  ```

- [ ] Old 02_add_aliases.sh marked as deprecated
  ```bash
  head -3 scripts/termux_ssh_toolkit/termux/02_add_aliases.sh | grep -i deprecated
  ```

- [ ] Documentation updated (AGENT_HANDOFF.md section 25)
  ```bash
  grep -q "Termux toolkit bootstrap refactor" docs/AGENT_HANDOFF.md
  ```

- [ ] BASHRC_REFACTOR_GUIDE.md exists
  ```bash
  [ -f docs/BASHRC_REFACTOR_GUIDE.md ] && echo "OK"
  ```

- [ ] No hardcoded IPs/users in scripts (all {{PLACEHOLDERS}})
  ```bash
  grep -n "192.168\|MiBookPro" scripts/termux_ssh_toolkit/shared/toolkit_functions.sh || echo "OK (no hardcodes found)"
  ```

- [ ] Russian text in whelp_ru.txt is preserved
  ```bash
  grep -E '[а-яА-ЯЁё]' scripts/termux_ssh_toolkit/shared/whelp_ru.txt | wc -l
  # Should be >100
  ```

---

## 6. POST-DEPLOYMENT SMOKE-CHECK (for users)

After merge to main branch, users should run:

```bash
# 1. Clone/update repo
cd ~/iikoinvoicebot
git pull --ff-only

# 2. Install toolkit
bash scripts/termux_ssh_toolkit/termux/install.sh \
  --win-user MiBookPro \
  --win-host 192.168.1.100 \
  --skip-keygen

# 3. Run smoke checks
source ~/.bashrc
bash scripts/termux_ssh_toolkit/termux/smoke_check.sh

# 4. Test core functions
wstatus  # SSH test
whelp | head -20  # Help output
wmailbox status  # Mailbox test

# 5. E2E wring test
wmailbox reply "echo 'Test' && date"
wring
# Check result:
wmailbox termux | tail -10
```

---

## 7. MONITORING & TROUBLESHOOTING

### If issues occur:

**Check 1: Encoding**
```bash
echo "Проверка русского" > /tmp/test.txt
cat /tmp/test.txt
# Should display Russian correctly
```

**Check 2: SSH**
```bash
wstatus  # This tests SSH
# If fails: Check IP with wsetip
```

**Check 3: Mailbox**
```bash
wmailbox status  # Check mailbox state
wmailbox list  # List inbox files
```

**Check 4: Toolkit**
```bash
ls -la ~/.config/windev/
cat ~/.config/windev/.version
bash -n ~/.config/windev/toolkit.sh
```

**Check 5: Syntax**
```bash
bash -n ~/.bashrc
bash -n ~/.config/windev/toolkit.sh
```

---

## SUMMARY VALIDATION TABLE

| Component | Check | Expected | Critical |
|-----------|-------|----------|----------|
| ~/.bashrc | bash -n | 0 | ✓ |
| toolkit.sh | bash -n | 0 | ✓ |
| wmailbox | command -v | exists | ✓ |
| whelp | wc -l | >50 lines | ✓ |
| whelp | Russian text | readable | ✓ |
| Encoding | file -i | utf-8 | ✓ |
| Line endings | grep CRLF | not found | ✓ |
| SSH | wstatus | works | ✓ |
| wring e2e | wring test | [ok] or [warn] | ✓ |

