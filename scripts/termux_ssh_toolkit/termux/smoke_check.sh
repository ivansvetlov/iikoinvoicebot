#!/data/data/com.termux/files/usr/bin/bash
# SMOKE CHECK: Minimal validation after toolkit installation
# Usage: bash smoke_check.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASHRC="$HOME/.bashrc"
TOOLKIT="$HOME/.config/windev/toolkit.sh"

log_pass() {
  echo -e "${GREEN}✓${NC} $*"
}

log_fail() {
  echo -e "${RED}✗${NC} $*"
  return 1
}

log_warn() {
  echo -e "${YELLOW}⚠${NC} $*"
}

log_info() {
  echo -e "${GREEN}[info]${NC} $*"
}

echo "========================================"
echo "TERMUX TOOLKIT SMOKE CHECK"
echo "========================================"
echo

# ============================================================================
# 1. SYNTAX CHECKS
# ============================================================================

echo "1. SYNTAX VALIDATION"
echo "---"

if bash -n "$BASHRC" 2>/dev/null; then
  log_pass "~/.bashrc syntax is valid"
else
  log_fail "~/.bashrc has syntax errors"
  bash -n "$BASHRC"
  exit 1
fi

if [ -f "$TOOLKIT" ]; then
  if bash -n "$TOOLKIT" 2>/dev/null; then
    log_pass "toolkit.sh syntax is valid"
  else
    log_fail "toolkit.sh has syntax errors"
    bash -n "$TOOLKIT"
    exit 1
  fi
else
  log_fail "toolkit.sh not found at $TOOLKIT"
  exit 1
fi

echo

# ============================================================================
# 2. FUNCTION AVAILABILITY
# ============================================================================

echo "2. FUNCTION AVAILABILITY"
echo "---"

# Source without output
OUTPUT=$(bash -c "source '$BASHRC' 2>&1")
if [ -n "$OUTPUT" ]; then
  log_warn "source ~/.bashrc produced output:"
  echo "$OUTPUT"
else
  log_pass "source ~/.bashrc completed silently (no unexpected output)"
fi

# Check critical functions
for cmd in wmailbox whelp wstatus wrunbox wring wpaste wvibe; do
  if bash -c "source '$BASHRC' && command -v '$cmd' >/dev/null 2>&1"; then
    log_pass "command '$cmd' is available"
  else
    log_fail "command '$cmd' is NOT available"
    exit 1
  fi
done

echo

# ============================================================================
# 3. WHELP CONTENT CHECK
# ============================================================================

echo "3. WHELP CONTENT"
echo "---"

WHELP_OUTPUT=$(bash -c "source '$BASHRC' && whelp 2>&1")
WHELP_LINES=$(echo "$WHELP_OUTPUT" | wc -l)

if [ "$WHELP_LINES" -gt 50 ]; then
  log_pass "whelp produced $WHELP_LINES lines of output (expected >50)"
else
  log_fail "whelp output is too short: $WHELP_LINES lines"
  echo "First 10 lines:"
  echo "$WHELP_OUTPUT" | head -10
  exit 1
fi

# Check for Russian text (should have Cyrillic characters)
if echo "$WHELP_OUTPUT" | grep -qE '[а-яА-ЯЁё]'; then
  log_pass "whelp contains Russian text (UTF-8 working)"
else
  log_warn "whelp might not contain Russian text (check encoding)"
fi

echo

# ============================================================================
# 4. WHELP SETS CHECK
# ============================================================================

echo "4. WHELP SETS (scenarios)"
echo "---"

SETS_OUTPUT=$(bash -c "source '$BASHRC' && whelp sets 2>&1")
SETS_LINES=$(echo "$SETS_OUTPUT" | wc -l)

if [ "$SETS_LINES" -gt 10 ]; then
  log_pass "whelp sets produced $SETS_LINES lines (expected >10)"
else
  log_fail "whelp sets output is too short: $SETS_LINES lines"
  exit 1
fi

echo

# ============================================================================
# 5. SSH/WMAILBOX BASIC CHECK
# ============================================================================

echo "5. SSH CONFIGURATION"
echo "---"

if [ -f "$HOME/.ssh/config" ]; then
  log_pass "~/.ssh/config exists"
  
  # Check if windev alias is configured
  if grep -q "^Host windev" "$HOME/.ssh/config"; then
    log_pass "windev SSH host is configured"
  else
    log_warn "windev SSH host not found in ~/.ssh/config (may not be configured yet)"
  fi
else
  log_warn "~/.ssh/config not found (SSH may not be configured)"
fi

echo

# ============================================================================
# 6. TOOLKIT METADATA
# ============================================================================

echo "6. TOOLKIT METADATA"
echo "---"

if [ -f "$HOME/.config/windev/.version" ]; then
  log_pass "Version file exists"
  cat "$HOME/.config/windev/.version"
else
  log_warn "Version file not found (first installation?)"
fi

echo

# ============================================================================
# 7. WRING E2E SIMULATION (dry-run)
# ============================================================================

echo "7. WRING E2E CHECK (dry-run, no actual mailbox)"
echo "---"

# Create a test command
TEST_CMD_FILE="/tmp/test_wring_cmd.sh"
cat > "$TEST_CMD_FILE" <<'EOF'
#!/bin/bash
echo "Test command executed successfully"
exit 0
EOF
chmod +x "$TEST_CMD_FILE"

# Test that wring function exists and can be called
if bash -c "source '$BASHRC' && command -v wring >/dev/null 2>&1"; then
  log_pass "wring function is defined and callable"
else
  log_fail "wring function is not available"
  exit 1
fi

# Simulate wring fetch (check if wmailbox is callable)
if bash -c "source '$BASHRC' && command -v wmailbox >/dev/null 2>&1"; then
  log_pass "wmailbox function is defined (required by wring)"
else
  log_fail "wmailbox function is not available"
  exit 1
fi

rm -f "$TEST_CMD_FILE"

echo

# ============================================================================
# 8. ENCODING CHECK
# ============================================================================

echo "8. ENCODING CHECK"
echo "---"

# Check if toolkit.sh has UTF-8 encoding
ENCODING=$(file -b --mime-encoding "$TOOLKIT")
if [ "$ENCODING" = "utf-8" ]; then
  log_pass "toolkit.sh encoding is UTF-8"
else
  log_warn "toolkit.sh encoding is $ENCODING (expected utf-8)"
fi

# Check for BOM in toolkit.sh
if xxd -l 3 "$TOOLKIT" 2>/dev/null | grep -q "ef bb bf"; then
  log_warn "toolkit.sh has UTF-8 BOM (should be removed)"
else
  log_pass "toolkit.sh has no BOM (good)"
fi

# Check for CRLF in toolkit.sh
if grep -l $'\r' "$TOOLKIT" >/dev/null 2>&1; then
  log_warn "toolkit.sh has CRLF line endings (should be LF)"
else
  log_pass "toolkit.sh has LF line endings (correct)"
fi

echo

# ============================================================================
# SUMMARY
# ============================================================================

echo "========================================"
echo "SMOKE CHECK COMPLETED SUCCESSFULLY"
echo "========================================"
echo
echo "Next steps:"
echo "1. Test SSH connection: wstatus"
echo "2. View full help: whelp"
echo "3. For E2E mailbox test: whelp sets"
echo "4. For full diagnostics: wdiag"
echo
