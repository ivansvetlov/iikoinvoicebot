param(
    [Parameter(Mandatory = $true)]
    [string]$CommandName,
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
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

$procCtl = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\05_phone_process_control.ps1"
$vibeShim = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\07_wvibe_windows_shim.ps1"
$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"

function Invoke-ProcessCtl {
    param(
        [Parameter(Mandatory = $true)][string]$Action,
        [string]$Target = "all"
    )
    if (-not (Test-Path -LiteralPath $procCtl)) {
        throw "Process control script not found: $procCtl"
    }
    & $procCtl -Action $Action -Target $Target -ProjectPath $ProjectPath | Out-Host
    return $LASTEXITCODE
}

function Invoke-ProjectPython {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python venv not found: $venvPython"
    }
    & $venvPython @Arguments | Out-Host
    return $LASTEXITCODE
}

function Run-Status {
    Set-Location -LiteralPath $ProjectPath
    & git status -sb | Out-Host
    if ($LASTEXITCODE -ne 0) { return $LASTEXITCODE }
    & git branch --show-current | Out-Host
    return $LASTEXITCODE
}

function Run-Smoke {
    Set-Location -LiteralPath $ProjectPath
    $ec = Invoke-ProjectPython -Arguments @("scripts\dev_status.py")
    if ($ec -ne 0) { return $ec }

    try {
        Invoke-RestMethod "http://127.0.0.1:8000/health" | ConvertTo-Json -Compress | Out-Host
    } catch {
        Write-Host "health: unavailable"
    }

    try {
        Invoke-RestMethod "http://127.0.0.1:8000/metrics/summary?window_minutes=60" | ConvertTo-Json -Compress | Out-Host
    } catch {
        Write-Host "metrics: unavailable"
    }
    return 0
}

function Show-Help {
    @"
Команды Windows toolkit:
  whelp                    Показать эту справку
  wproj                    Показать путь проекта
  wstatus                  git status -sb + текущая ветка
  wpull                    git pull --ff-only
  wps                      Статус сервисов
  wstart [target]          Запустить сервисы: all|backend|worker|bot
  wstop [target]           Остановить сервисы
  wrestart [target]        Перезапустить сервисы
  wtail [target|file]      Смотреть логи (worker/backend/bot или имя файла)
  wlogs [target|file]      Алиас для wtail
  wdevstatus               Запустить scripts/dev_status.py
  wmetrics [args]          Запустить scripts/metrics_report.py (по умолчанию --minutes 60)
  wsmoke                   dev_status + /health + /metrics/summary
  wdiag                    host + git + services + smoke
  wtest                    Запустить unittest
  wdeploy [--dry-run|--yes]
  wrun [monitor|incident|recover|release]
  wvibe ...                Обертка над Vibe
  wreconnect               Алиас для: wvibe reconnect
  wmcp "<точная команда>"  Алиас для: wvibe mcp ...
  waider                   Запустить aider в проекте
"@ | Write-Output
}

$cmd = $CommandName.ToLowerInvariant()
$exitCode = 0

switch ($cmd) {
    "whelp" {
        Show-Help
    }
    "wh" {
        Show-Help
    }
    "wproj" {
        Write-Output $ProjectPath
    }
    "wstatus" {
        $exitCode = Run-Status
    }
    "wpull" {
        Set-Location -LiteralPath $ProjectPath
        & git pull --ff-only
        $exitCode = $LASTEXITCODE
    }
    "wstart" {
        $target = if ($Args.Count -gt 0) { $Args[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "start" -Target $target
    }
    "wstop" {
        $target = if ($Args.Count -gt 0) { $Args[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "stop" -Target $target
    }
    "wrestart" {
        $target = if ($Args.Count -gt 0) { $Args[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "restart" -Target $target
    }
    "wps" {
        $exitCode = Invoke-ProcessCtl -Action "status" -Target "all"
    }
    "wtail" {
        $sel = if ($Args.Count -gt 0) { $Args[0] } else { "worker" }
        $file = switch ($sel) {
            "backend" { "backend.log" }
            "worker" { "worker.log" }
            "bot" { "bot.log" }
            default { $sel }
        }
        $logPath = Join-Path $ProjectPath "logs\$file"
        if (-not (Test-Path -LiteralPath $logPath)) {
            throw "Log file not found: $logPath"
        }
        Get-Content -LiteralPath $logPath -Tail 120 -Wait
    }
    "wlogs" {
        $tailArgs = @("-CommandName", "wtail", "-ProjectPath", $ProjectPath, "-UvBinPath", $UvBinPath)
        if ($Args.Count -gt 0) {
            $tailArgs += $Args
        }
        & $PSCommandPath @tailArgs
        $exitCode = $LASTEXITCODE
    }
    "wdevstatus" {
        Set-Location -LiteralPath $ProjectPath
        $exitCode = Invoke-ProjectPython -Arguments @("scripts\dev_status.py")
    }
    "wmetrics" {
        Set-Location -LiteralPath $ProjectPath
        $metricsArgs = @("scripts\metrics_report.py")
        if ($Args.Count -eq 0) {
            $metricsArgs += @("--minutes", "60")
        } else {
            $metricsArgs += $Args
        }
        $exitCode = Invoke-ProjectPython -Arguments $metricsArgs
    }
    "wsmoke" {
        $exitCode = Run-Smoke
    }
    "wdiag" {
        Write-Host "=== HOST ==="
        hostname
        whoami
        Write-Host ""
        Write-Host "=== GIT ==="
        $exitCode = Run-Status
        if ($exitCode -ne 0) { break }
        Write-Host ""
        Write-Host "=== SERVICES ==="
        $exitCode = Invoke-ProcessCtl -Action "status" -Target "all"
        if ($exitCode -ne 0) { break }
        Write-Host ""
        Write-Host "=== SMOKE ==="
        $exitCode = Run-Smoke
    }
    "wtest" {
        Set-Location -LiteralPath $ProjectPath
        $exitCode = Invoke-ProjectPython -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")
    }
    "wdeploy" {
        $dryRun = $false
        $forceYes = $false
        foreach ($arg in $Args) {
            switch ($arg) {
                "--dry-run" { $dryRun = $true; continue }
                "--yes" { $forceYes = $true; continue }
                default { throw "Неизвестная опция: $arg. Использование: wdeploy [--dry-run] [--yes]" }
            }
        }

        Write-Output "[plan] 1) wpull"
        Write-Output "[plan] 2) wtest"
        Write-Output "[plan] 3) wrestart all"
        Write-Output "[plan] 4) wsmoke"

        if ($dryRun) { break }
        if (-not $forceYes) {
            $answer = Read-Host "Запустить deploy-цикл? [y/N]"
            if ($answer -notmatch "^(y|Y|yes|YES)$") {
                $exitCode = 1
                break
            }
        }

        Set-Location -LiteralPath $ProjectPath
        & git pull --ff-only
        if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE; break }

        $exitCode = Invoke-ProjectPython -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")
        if ($exitCode -ne 0) { break }

        $exitCode = Invoke-ProcessCtl -Action "restart" -Target "all"
        if ($exitCode -ne 0) { break }

        $exitCode = Run-Smoke
    }
    "wrun" {
        if ($Args.Count -eq 0) {
            throw "Использование: wrun [monitor|incident|recover|release]"
        }
        switch ($Args[0].ToLowerInvariant()) {
            "monitor" {
                $exitCode = Invoke-ProcessCtl -Action "status" -Target "all"
                if ($exitCode -ne 0) { break }
                Set-Location -LiteralPath $ProjectPath
                $exitCode = Invoke-ProjectPython -Arguments @("scripts\metrics_report.py", "--minutes", "60")
            }
            "incident" {
                Write-Host "=== HOST ==="
                hostname
                whoami
                Write-Host ""
                Write-Host "=== GIT ==="
                $exitCode = Run-Status
                if ($exitCode -ne 0) { break }
                Write-Host ""
                Write-Host "=== SERVICES ==="
                $exitCode = Invoke-ProcessCtl -Action "status" -Target "all"
                if ($exitCode -ne 0) { break }
                Write-Host ""
                Write-Host "=== SMOKE ==="
                $exitCode = Run-Smoke
                if ($exitCode -ne 0) { break }
                $workerLog = Join-Path $ProjectPath "logs\worker.log"
                if (-not (Test-Path -LiteralPath $workerLog)) {
                    throw "Log file not found: $workerLog"
                }
                Get-Content -LiteralPath $workerLog -Tail 120 -Wait
            }
            "recover" {
                $exitCode = Invoke-ProcessCtl -Action "restart" -Target "all"
                if ($exitCode -ne 0) { break }
                $exitCode = Run-Smoke
                if ($exitCode -ne 0) { break }
                $exitCode = Run-Status
            }
            "release" {
                $exitCode = Run-Status
                if ($exitCode -ne 0) { break }
                Set-Location -LiteralPath $ProjectPath
                & git pull --ff-only
                if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE; break }
                $exitCode = Invoke-ProjectPython -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")
                if ($exitCode -ne 0) { break }
                $exitCode = Invoke-ProcessCtl -Action "restart" -Target "all"
                if ($exitCode -ne 0) { break }
                $exitCode = Run-Smoke
            }
            default {
                throw "Использование: wrun [monitor|incident|recover|release]"
            }
        }
    }
    "wvibe" {
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath @Args
        $exitCode = $LASTEXITCODE
    }
    "wreconnect" {
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath reconnect @Args
        $exitCode = $LASTEXITCODE
    }
    "wmcp" {
        if ($Args.Count -eq 0) {
            throw "Использование: wmcp ""<точная команда>"""
        }
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath mcp @Args
        $exitCode = $LASTEXITCODE
    }
    "waider" {
        $env:Path = "$UvBinPath;$env:Path"
        Set-Location -LiteralPath $ProjectPath
        & aider
        $exitCode = $LASTEXITCODE
    }
    "wgo" {
        $psExe = Join-Path $PSHOME "powershell.exe"
        if (-not (Test-Path -LiteralPath $psExe)) {
            $psExe = "powershell"
        }
        & $psExe -NoLogo -NoExit -Command "Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath `$env:USERPROFILE"
        $exitCode = $LASTEXITCODE
    }
    "wenter" {
        $psExe = Join-Path $PSHOME "powershell.exe"
        if (-not (Test-Path -LiteralPath $psExe)) {
            $psExe = "powershell"
        }
        & $psExe -NoLogo -NoExit -Command "Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath '$ProjectPath'"
        $exitCode = $LASTEXITCODE
    }
    default {
        throw "Неизвестная команда: $CommandName. Выполни whelp."
    }
}

exit $exitCode
