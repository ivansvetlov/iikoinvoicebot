param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$defaultProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (
    -not (Test-Path -LiteralPath $ProjectPath) -and
    -not ($ProjectPath -match "[\\/]" -or $ProjectPath -match "^[A-Za-z]:")
) {
    $Args = @($ProjectPath) + $Args
    $ProjectPath = $defaultProjectPath
}

$wrapper = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\06_run_vibe_wrapper.ps1"
if (-not (Test-Path -LiteralPath $wrapper)) {
    throw "Wrapper not found: $wrapper"
}

$mode = "start"
$skipBootstrap = $false
$forceCleanup = $false
$enableMcp = $false
$askMaxTurns = $null
$taskParts = @()

$i = 0
while ($i -lt $Args.Count) {
    $arg = $Args[$i]
    switch -Regex ($arg) {
        "^(reconnect|rc)$" { $mode = "reconnect"; $i++; continue }
        "^(stop|kill)$" { $mode = "stop"; $i++; continue }
        "^(doctor|diag|ps)$" { $mode = "doctor"; $i++; continue }
        "^(ask|text)$" { if ($mode -eq "start") { $mode = "ask" }; $i++; continue }
        "^mcp$" { if ($mode -eq "start") { $mode = "mcp_cmd" }; $i++; continue }
        "^--no-bootstrap$" { $skipBootstrap = $true; $i++; continue }
        "^--force$" { $forceCleanup = $true; $i++; continue }
        "^--mcp$" { $enableMcp = $true; $i++; continue }
        "^--max-turns=(\d+)$" {
            $askMaxTurns = [int]$matches[1]
            $i++
            continue
        }
        "^--max-turns$" {
            if ($i + 1 -ge $Args.Count) {
                throw "Expected integer after --max-turns"
            }
            $next = $Args[$i + 1]
            $parsed = 0
            if (-not [int]::TryParse($next, [ref]$parsed)) {
                throw "Invalid value for --max-turns: $next"
            }
            $askMaxTurns = $parsed
            $i += 2
            continue
        }
        default {
            $taskParts += $arg
            $i++
            continue
        }
    }
}

if ($mode -eq "mcp_cmd" -and $taskParts.Count -eq 0) {
    Write-Host "Usage: wvibe mcp <exact command>"
    exit 1
}

$taskBase64 = ""
if ($taskParts.Count -gt 0) {
    $task = [string]::Join(" ", $taskParts)
    $taskBase64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($task))
}

$invokeArgs = @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $wrapper,
    "-ProjectPath", $ProjectPath,
    "-UvBinPath", $UvBinPath,
    "-Mode", $mode
)

if ($skipBootstrap) {
    $invokeArgs += "-SkipBootstrap"
}
if ($forceCleanup) {
    $invokeArgs += "-ForceCleanup"
}
if ($enableMcp) {
    $invokeArgs += "-EnableMcp"
}
if ($null -ne $askMaxTurns) {
    $invokeArgs += @("-AskMaxTurns", [string]$askMaxTurns)
}
if (-not [string]::IsNullOrWhiteSpace($taskBase64)) {
    $invokeArgs += @("-TaskBase64", $taskBase64)
}

$psExe = Join-Path $PSHOME "powershell.exe"
if (-not (Test-Path -LiteralPath $psExe)) {
    $psExe = "powershell"
}

& $psExe @invokeArgs
exit $LASTEXITCODE
