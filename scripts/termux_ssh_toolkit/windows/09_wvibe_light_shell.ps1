param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin",
    [switch]$WithBootstrap,
    [string]$Task = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

if (-not (Test-Path -LiteralPath $ProjectPath)) {
    throw "Project path not found: $ProjectPath"
}

$shimPath = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\07_wvibe_windows_shim.ps1"
if (-not (Test-Path -LiteralPath $shimPath)) {
    throw "Shim script not found: $shimPath"
}

function Show-LocalHelp {
    @"
Легкая оболочка Vibe:
  Вводи задачу одной строкой и жми Enter.
  Команды:
    /help        показать эту справку
    /doctor      проверить состояние wrapper
    /reconnect   продолжить последнюю сессию
    /bootstrap   включить bootstrap на следующий запрос
    /noboot      выключить bootstrap (по умолчанию)
    /exit        выйти
"@ | Out-Host
}

$useBootstrap = $WithBootstrap.IsPresent

if (-not [string]::IsNullOrWhiteSpace($Task)) {
    if ($useBootstrap) {
        & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask $Task
    } else {
        & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --no-bootstrap $Task
    }
    exit $LASTEXITCODE
}

Write-Host "Легкая оболочка Vibe запущена."
if ($useBootstrap) {
    Write-Host "Режим: bootstrap включен."
} else {
    Write-Host "Режим: без bootstrap."
}
Write-Host "Напиши /help для списка команд."

while ($true) {
    $line = Read-Host "vibe>"
    if ($null -eq $line) {
        continue
    }

    $cmd = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($cmd)) {
        continue
    }

    switch -Regex ($cmd) {
        "^(\/exit|exit|quit|q)$" {
            break
        }
        "^(\/help|\?)$" {
            Show-LocalHelp
            continue
        }
        "^\/doctor$" {
            & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath doctor
            continue
        }
        "^\/reconnect$" {
            & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath reconnect
            continue
        }
        "^\/bootstrap$" {
            $useBootstrap = $true
            Write-Host "bootstrap: on"
            continue
        }
        "^\/noboot$" {
            $useBootstrap = $false
            Write-Host "bootstrap: off"
            continue
        }
        default {
            try {
                if ($useBootstrap) {
                    & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask $cmd
                } else {
                    & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --no-bootstrap $cmd
                }
            } catch {
                Write-Host "[error] $($_.Exception.Message)"
            }
        }
    }
}

Write-Host "Выход из легкой оболочки Vibe."
