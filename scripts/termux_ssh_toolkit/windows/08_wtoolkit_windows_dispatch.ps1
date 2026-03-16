param(
    [Parameter(Mandatory = $true)]
    [string]$CommandName,
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
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
$vibeLightShell = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\09_wvibe_light_shell.ps1"
$mailboxTool = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\10_mailbox.ps1"
$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$sharedDir = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\shared"
$helpRu = Join-Path $sharedDir "whelp_ru.txt"
$helpSetsRu = Join-Path $sharedDir "whelp_sets_ru.txt"
if ($null -eq $CommandArgs) {
    $CommandArgs = @()
} elseif ($CommandArgs -is [string]) {
    $CommandArgs = @($CommandArgs)
}

function Get-LastCodeOrZero {
    $var = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($null -eq $var) {
        return 0
    }
    return [int]$var.Value
}

function Invoke-ProcessCtl {
    param(
        [Parameter(Mandatory = $true)][string]$Action,
        [string]$Target = "all"
    )
    if (-not (Test-Path -LiteralPath $procCtl)) {
        throw "Process control script not found: $procCtl"
    }
    & $procCtl -Action $Action -Target $Target -ProjectPath $ProjectPath | Out-Host
    return (Get-LastCodeOrZero)
}

function Invoke-ProjectPython {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python venv not found: $venvPython"
    }
    & $venvPython @Arguments | Out-Host
    return (Get-LastCodeOrZero)
}

function Run-Status {
    Set-Location -LiteralPath $ProjectPath
    & git status -sb | Out-Host
    $gitStatusCode = Get-LastCodeOrZero
    if ($gitStatusCode -ne 0) { return $gitStatusCode }
    & git branch --show-current | Out-Host
    return (Get-LastCodeOrZero)
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
    param([string]$Topic = "all")

    if ($Topic -in @("sets", "set", "scenarios", "scenario")) {
        if (Test-Path -LiteralPath $helpSetsRu) {
            Get-Content -LiteralPath $helpSetsRu -Encoding UTF8 | Out-Host
            return
        }
        Write-Output "Файл наборов команд не найден: $helpSetsRu"
        return
    }

    if (Test-Path -LiteralPath $helpRu) {
        Get-Content -LiteralPath $helpRu -Encoding UTF8 | Out-Host
        return
    }

    Write-Output "Файл справки не найден: $helpRu"
}

$cmd = $CommandName.ToLowerInvariant()
$exitCode = 0

switch ($cmd) {
    "whelp" {
        $topic = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "all" }
        Show-Help -Topic $topic
    }
    "wh" {
        $topic = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "all" }
        Show-Help -Topic $topic
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
        $exitCode = Get-LastCodeOrZero
    }
    "wstart" {
        $target = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "start" -Target $target
    }
    "wstop" {
        $target = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "stop" -Target $target
    }
    "wrestart" {
        $target = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "all" }
        $exitCode = Invoke-ProcessCtl -Action "restart" -Target $target
    }
    "wps" {
        $exitCode = Invoke-ProcessCtl -Action "status" -Target "all"
    }
    "wtail" {
        $sel = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "worker" }
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
        if ($CommandArgs.Count -gt 0) {
            $tailArgs += $CommandArgs
        }
        & $PSCommandPath @tailArgs
        $exitCode = Get-LastCodeOrZero
    }
    "wdevstatus" {
        Set-Location -LiteralPath $ProjectPath
        $exitCode = Invoke-ProjectPython -Arguments @("scripts\dev_status.py")
    }
    "wmetrics" {
        Set-Location -LiteralPath $ProjectPath
        $metricsArgs = @("scripts\metrics_report.py")
        if ($CommandArgs.Count -eq 0) {
            $metricsArgs += @("--minutes", "60")
        } else {
            $metricsArgs += $CommandArgs
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
        foreach ($arg in $CommandArgs) {
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
        $pullCode = Get-LastCodeOrZero
        if ($pullCode -ne 0) { $exitCode = $pullCode; break }

        $exitCode = Invoke-ProjectPython -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")
        if ($exitCode -ne 0) { break }

        $exitCode = Invoke-ProcessCtl -Action "restart" -Target "all"
        if ($exitCode -ne 0) { break }

        $exitCode = Run-Smoke
    }
    "wrun" {
        if ($CommandArgs.Count -eq 0) {
            throw "Использование: wrun [monitor|incident|recover|release]"
        }
        switch ($CommandArgs[0].ToLowerInvariant()) {
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
                $releasePullCode = Get-LastCodeOrZero
                if ($releasePullCode -ne 0) { $exitCode = $releasePullCode; break }
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
    "wplan" {
        if (-not (Test-Path -LiteralPath $mailboxTool)) {
            throw "Mailbox tool not found: $mailboxTool"
        }
        if ($CommandArgs.Count -eq 0) {
            throw "Использование: wplan <текст задачи>"
        }
        $taskText = [string]::Join(" ", $CommandArgs)
        & $mailboxTool -Action plan -ProjectPath $ProjectPath -Source "windows" -Text $taskText
        $exitCode = Get-LastCodeOrZero
    }
    "wmailbox" {
        if (-not (Test-Path -LiteralPath $mailboxTool)) {
            throw "Mailbox tool not found: $mailboxTool"
        }
        $sub = if ($CommandArgs.Count -gt 0) { $CommandArgs[0].ToLowerInvariant() } else { "status" }
        switch ($sub) {
            "ensure" {
                & $mailboxTool -Action ensure -ProjectPath $ProjectPath
            }
            "status" {
                & $mailboxTool -Action status -ProjectPath $ProjectPath
            }
            "list" {
                & $mailboxTool -Action list -ProjectPath $ProjectPath
            }
            "digest" {
                & $mailboxTool -Action digest -ProjectPath $ProjectPath
            }
            "show" {
                & $mailboxTool -Action show -ProjectPath $ProjectPath
            }
            "prompt" {
                & $mailboxTool -Action prompt -ProjectPath $ProjectPath
            }
            "handoff" {
                & $mailboxTool -Action handoff -ProjectPath $ProjectPath
            }
            "resolve" {
                if ($CommandArgs.Count -lt 2) {
                    throw "Использование: wmailbox resolve <file1.md> [file2.md ...]"
                }
                $items = @()
                for ($j = 1; $j -lt $CommandArgs.Count; $j++) {
                    $items += $CommandArgs[$j]
                }
                & $mailboxTool -Action resolve -ProjectPath $ProjectPath -Items $items
            }
            default {
                throw "Использование: wmailbox [ensure|status|list|digest|show|prompt|handoff|resolve]"
            }
        }
        $exitCode = Get-LastCodeOrZero
    }
    "wvibe" {
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath @CommandArgs
        $exitCode = Get-LastCodeOrZero
    }
    "wreconnect" {
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath reconnect @CommandArgs
        $exitCode = Get-LastCodeOrZero
    }
    "wmcp" {
        if ($CommandArgs.Count -eq 0) {
            throw "Использование: wmcp ""<точная команда>"""
        }
        if (-not (Test-Path -LiteralPath $vibeShim)) {
            throw "Vibe shim not found: $vibeShim"
        }
        & $vibeShim -ProjectPath $ProjectPath -UvBinPath $UvBinPath mcp @CommandArgs
        $exitCode = Get-LastCodeOrZero
    }
    "waider" {
        $env:Path = "$UvBinPath;$env:Path"
        Set-Location -LiteralPath $ProjectPath
        & aider
        $exitCode = Get-LastCodeOrZero
    }
    "wvshell" {
        if (-not (Test-Path -LiteralPath $vibeLightShell)) {
            throw "Light shell script not found: $vibeLightShell"
        }

        $withBootstrap = $false
        $enableMcp = $false
        $askMaxTurns = 8
        $taskParts = @()
        for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
            $a = $CommandArgs[$i]
            switch ($a) {
                "--bootstrap" {
                    $withBootstrap = $true
                    continue
                }
                "-WithBootstrap" {
                    $withBootstrap = $true
                    continue
                }
                "--noboot" {
                    $withBootstrap = $false
                    continue
                }
                "--mcp" {
                    $enableMcp = $true
                    continue
                }
                "--turns" {
                    if ($i + 1 -ge $CommandArgs.Count) {
                        throw "Для --turns нужно указать число."
                    }
                    $i++
                    $parsedTurns = 0
                    if (-not [int]::TryParse($CommandArgs[$i], [ref]$parsedTurns)) {
                        throw "Неверное значение --turns: $($CommandArgs[$i])"
                    }
                    $askMaxTurns = $parsedTurns
                    continue
                }
                default {
                    $taskParts += $a
                }
            }
        }

        if ($taskParts.Count -gt 0) {
            $taskText = [string]::Join(" ", $taskParts)
            if ($withBootstrap) {
                if ($enableMcp) {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -WithBootstrap -EnableMcp -AskMaxTurns $askMaxTurns -Task $taskText
                } else {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -WithBootstrap -AskMaxTurns $askMaxTurns -Task $taskText
                }
            } else {
                if ($enableMcp) {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -EnableMcp -AskMaxTurns $askMaxTurns -Task $taskText
                } else {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -AskMaxTurns $askMaxTurns -Task $taskText
                }
            }
        } else {
            if ($withBootstrap) {
                if ($enableMcp) {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -WithBootstrap -EnableMcp -AskMaxTurns $askMaxTurns
                } else {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -WithBootstrap -AskMaxTurns $askMaxTurns
                }
            } else {
                if ($enableMcp) {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -EnableMcp -AskMaxTurns $askMaxTurns
                } else {
                    & $vibeLightShell -ProjectPath $ProjectPath -UvBinPath $UvBinPath -AskMaxTurns $askMaxTurns
                }
            }
        }
        $exitCode = Get-LastCodeOrZero
    }
    "wgo" {
        $psExe = Join-Path $PSHOME "powershell.exe"
        if (-not (Test-Path -LiteralPath $psExe)) {
            $psExe = "powershell"
        }
        & $psExe -NoLogo -NoExit -Command "Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath `$env:USERPROFILE"
        $exitCode = Get-LastCodeOrZero
    }
    "wenter" {
        $psExe = Join-Path $PSHOME "powershell.exe"
        if (-not (Test-Path -LiteralPath $psExe)) {
            $psExe = "powershell"
        }
        & $psExe -NoLogo -NoExit -Command "Import-Module PSReadLine -ErrorAction SilentlyContinue; Set-Location -LiteralPath '$ProjectPath'"
        $exitCode = Get-LastCodeOrZero
    }
    default {
        throw "Неизвестная команда: $CommandName. Выполни whelp."
    }
}

exit $exitCode
