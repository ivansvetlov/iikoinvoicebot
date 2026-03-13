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
$taskParts = @()

foreach ($arg in $Args) {
    switch ($arg) {
        "reconnect" { $mode = "reconnect"; continue }
        "rc" { $mode = "reconnect"; continue }
        "stop" { $mode = "stop"; continue }
        "kill" { $mode = "stop"; continue }
        "doctor" { $mode = "doctor"; continue }
        "diag" { $mode = "doctor"; continue }
        "ps" { $mode = "doctor"; continue }
        "ask" { if ($mode -eq "start") { $mode = "ask"; continue } }
        "text" { if ($mode -eq "start") { $mode = "ask"; continue } }
        "mcp" { if ($mode -eq "start") { $mode = "mcp_cmd"; continue } }
        "--no-bootstrap" { $skipBootstrap = $true; continue }
        "--force" { $forceCleanup = $true; continue }
        default {
            $taskParts += $arg
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
if (-not [string]::IsNullOrWhiteSpace($taskBase64)) {
    $invokeArgs += @("-TaskBase64", $taskBase64)
}

$psExe = Join-Path $PSHOME "powershell.exe"
if (-not (Test-Path -LiteralPath $psExe)) {
    $psExe = "powershell"
}

& $psExe @invokeArgs
exit $LASTEXITCODE
