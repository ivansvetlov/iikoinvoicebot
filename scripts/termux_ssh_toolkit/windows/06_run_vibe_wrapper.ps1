param(
    [string]$ProjectPath = "C:\Users\MiBookPro\PycharmProjects\PythonProject",
    [string]$UvBinPath = "C:\Users\MiBookPro\.local\bin",
    [string]$Task = ""
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

if ([string]::IsNullOrWhiteSpace($Task)) {
    & $vibeExe @agentArgs
    exit $LASTEXITCODE
}

$wrappedPrompt = @"
Ты работаешь в проекте iikoinvoicebot как практичный инженер.
Выполняй задачу до результата: анализ -> изменения -> проверка -> краткий отчет.
Если задача расплывчатая, сначала уточни цель в 1-2 вопросах.
Если можно сделать безопасно без вопроса — делай.

Задача пользователя:
$Task
"@

& $vibeExe @agentArgs $wrappedPrompt
exit $LASTEXITCODE

