---
name: powershell-windows
description: "PowerShell Windows patterns. Critical pitfalls, operator syntax, error handling, agent-shell gotchas. Update section 10 when PS bugs are found in this project."
risk: unknown
source: community
date_added: "2026-02-27"
---

# PowerShell Windows Patterns

> Critical patterns and pitfalls for Windows PowerShell.

---

## 1. Operator Syntax Rules

### CRITICAL: Parentheses Required

| Wrong | Correct |
|----------|-----------|
| `if (Test-Path "a" -or Test-Path "b")` | `if ((Test-Path "a") -or (Test-Path "b"))` |
| `if (Get-Item $x -and $y -eq 5)` | `if ((Get-Item $x) -and ($y -eq 5))` |

**Rule:** Each cmdlet call MUST be in parentheses when using logical operators.

---

## 2. Unicode/Emoji Restriction

### CRITICAL: No Unicode in Scripts

| Purpose | Don't Use | Use |
|---------|-------------|--------|
| Success | checkmarks | [OK] [+] |
| Error | emoji | [!] [X] |
| Warning | emoji | [*] [WARN] |
| Info | emoji | [i] [INFO] |
| Progress | emoji | [...] |

**Rule:** Use ASCII characters only in PowerShell scripts.

---

## 3. Null Check Patterns

### Always Check Before Access

| Wrong | Correct |
|----------|-----------|
| `$array.Count -gt 0` | `$array -and $array.Count -gt 0` |
| `$text.Length` | `if ($text) { $text.Length }` |

---

## 4. String Interpolation

### Complex Expressions

| Wrong | Correct |
|----------|-----------|
| `"Value: $($obj.prop.sub)"` | Store in variable first |

**Pattern:**
```
$value = $obj.prop.sub
Write-Output "Value: $value"
```

---

## 5. Error Handling

### ErrorActionPreference

| Value | Use |
|-------|-----|
| Stop | Development (fail fast) |
| Continue | Production scripts |
| SilentlyContinue | When errors expected |

### Try/Catch Pattern

- Don't return inside try block
- Use finally for cleanup
- Return after try/catch

---

## 6. File Paths

### Windows Path Rules

| Pattern | Use |
|---------|-----|
| Literal path | `C:\Users\User\file.txt` |
| Variable path | `Join-Path $env:USERPROFILE "file.txt"` |
| Relative | `Join-Path $ScriptDir "data"` |

**Rule:** Use Join-Path for cross-platform safety.

---

## 7. Array Operations

### Correct Patterns

| Operation | Syntax |
|-----------|--------|
| Empty array | `$array = @()` |
| Add item | `$array += $item` |
| ArrayList add | `$list.Add($item) | Out-Null` |

---

## 8. JSON Operations

### CRITICAL: Depth Parameter

| Wrong | Correct |
|----------|-----------|
| `ConvertTo-Json` | `ConvertTo-Json -Depth 10` |

**Rule:** Always specify `-Depth` for nested objects.

### File Operations

| Operation | Pattern |
|-----------|---------|
| Read | `Get-Content "file.json" -Raw | ConvertFrom-Json` |
| Write | `$data | ConvertTo-Json -Depth 10 | Out-File "file.json" -Encoding UTF8` |

---

## 9. Common Errors

| Error Message | Cause | Fix |
|---------------|-------|-----|
| "parameter 'or'" | Missing parentheses | Wrap cmdlets in () |
| "Unexpected token" | Unicode character | Use ASCII only |
| "Cannot find property" | Null object | Check null first |
| "Cannot convert" | Type mismatch | Use .ToString() |
| "InvalidEndOfLine" / `&&` not valid | Bash chaining in PS 5.x | Use `;` or separate commands |
| "Missing ')'" on `(cd path; cmd)` | Invalid grouped `cd` one-liner | `Set-Location path` then run `cmd` |
| "NativeCommandError" on python INFO | stderr redirect `2>` captures stdout | Drop redirect or log inside Python |

---

## 10. Agent Shell Pitfalls (append here when PS bugs are found)

**Rule:** When a PowerShell issue is debugged in this project, add the pattern here — not only in chat/tmp.

### No Bash syntax in Windows PowerShell 5.x

| Bash habit | PowerShell fix |
|------------|----------------|
| `cmd1 && cmd2` | `cmd1; if ($LASTEXITCODE -eq 0) { cmd2 }` |
| `git commit -m "$(cat <<'EOF' ... EOF)"` | `git commit -m "single-line message"` |
| Leading `& 'path\python.exe'` in agent tools | Full path without leading `&` (some runners treat `&` as background) |

### Start-Process and detached children

- Agent shells use Windows **job objects** — `Popen`, `start /B`, `Start-Process`, and `pythonw` children die when the agent command exits. Use `scripts/dev_stack_ctl.py` (`schtasks /run` escape hatch).
- Tray monitor poll spawns PowerShell — must use `scripts/dev_ps_hidden.py` (`CREATE_NO_WINDOW` + `-WindowStyle Hidden`); visible `subprocess.check_output(['powershell',...])` flashes a console every ~5 s. Only one `pythonw` monitor instance.
- `Start-Process pythonw.exe` may exit soon after parent returns; tray apps may need a **launcher `.ps1`** or persistent parent terminal.
- PowerShell eats `$` in service names (`WireGuardTunnel$vpn188958_split_sotaocr`) — escape with backtick or use `cmd /c sc query WireGuardTunnel`$vpn188958_split_sotaocr``.
- Set `$env:PYTHONPATH` in the **same script** immediately before `Start-Process`.
- Git worktrees often lack `.venv` — resolve main repo:

```powershell
$MainRoot = (Resolve-Path (Join-Path $RepoRoot '..\..')).Path
$Pythonw = Join-Path $MainRoot '.venv\Scripts\pythonw.exe'
```

### Process inspection / cleanup

```powershell
Get-Process pythonw -ErrorAction SilentlyContinue  # exit 1 if none = normal
```

`Select-Object -SkipLast 1` on a **single** process kills it — check `.Count -gt 1` first.

### Agent one-liners

Use **absolute paths**; relative `..\.venv\Scripts\python.exe` fails when cwd differs.

---

## 11. Script Template

```powershell
# Strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Main
try {
    # Logic here
    Write-Output "[OK] Done"
    exit 0
}
catch {
    Write-Warning "Error: $_"
    exit 1
}
```

---

> **Remember:** PowerShell has unique syntax rules. Parentheses, ASCII-only, and null checks are non-negotiable.

## When to Use
This skill is applicable to execute the workflow or actions described in the overview.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.
