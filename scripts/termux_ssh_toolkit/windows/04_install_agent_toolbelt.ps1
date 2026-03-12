param(
    [switch]$InstallAider = $true,
    [switch]$InstallMistralVibe = $true,
    [switch]$InstallDevTools = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
if (-not (Test-Path -LiteralPath $uv)) {
    throw "uv.exe not found at $uv. Install uv first."
}

function Install-Or-UpgradeTool {
    param([Parameter(Mandatory = $true)][string]$ToolName)
    & $uv tool install $ToolName 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $uv tool upgrade $ToolName
    }
}

if ($InstallMistralVibe) {
    Write-Host "Installing/upgrading mistral-vibe..."
    Install-Or-UpgradeTool -ToolName "mistral-vibe"
}

if ($InstallAider) {
    Write-Host "Installing/upgrading aider-chat..."
    Install-Or-UpgradeTool -ToolName "aider-chat"
}

if ($InstallDevTools) {
    Write-Host "Installing/upgrading dev helper tools..."
    Install-Or-UpgradeTool -ToolName "pre-commit"
    Install-Or-UpgradeTool -ToolName "ruff"
}

Write-Host "Done. Available commands are in $($env:USERPROFILE)\.local\bin"

