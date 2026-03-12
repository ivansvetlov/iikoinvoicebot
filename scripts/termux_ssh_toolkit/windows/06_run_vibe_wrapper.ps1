param(
    [string]$ProjectPath = "C:\Users\MiBookPro\PycharmProjects\PythonProject",
    [string]$UvBinPath = "C:\Users\MiBookPro\.local\bin",
    [string]$Task = "",
    [ValidateSet("start", "reconnect")]
    [string]$Mode = "start",
    [switch]$SkipBootstrap
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectPath)) {
    throw "Project path not found: $ProjectPath"
}

$vibeExe = Join-Path $UvBinPath "vibe.exe"
if (-not (Test-Path -LiteralPath $vibeExe)) {
    throw "vibe.exe not found at $vibeExe"
}

$env:Path = "$UvBinPath;$env:Path"
Set-Location -LiteralPath $ProjectPath

$agentName = "phone-wrapper"
$agentFile = Join-Path $ProjectPath ".vibe\agents\phone-wrapper.toml"
$agentArgs = @()
if (Test-Path -LiteralPath $agentFile) {
    $agentArgs = @("--agent", $agentName)
}

if ($Mode -eq "reconnect") {
    & $vibeExe -c @agentArgs
    exit $LASTEXITCODE
}

function Get-BootstrapPrompt {
    return @"
Сначала выполни прогрев контекста по проекту:
1) Прочитай файлы:
   - docs/START_HERE_NEW_CHAT.md
   - docs/AGENT_HANDOFF.md
   - docs/TODO.md
   - docs/ARCHITECTURE.md
   - docs/README.md
   - VIBE.md
2) После чтения дай короткий статус:
   - done
   - in progress
   - next
   - risks/blockers
3) Затем переходи к работе по задаче пользователя.
"@
}

if ([string]::IsNullOrWhiteSpace($Task) -and $SkipBootstrap) {
    & $vibeExe @agentArgs
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($Task)) {
    $wrappedPrompt = Get-BootstrapPrompt
} else {
    $bootstrap = Get-BootstrapPrompt
    $wrappedPrompt = @"
$bootstrap

Задача пользователя:
$Task
"@
}

& $vibeExe @agentArgs $wrappedPrompt
exit $LASTEXITCODE

