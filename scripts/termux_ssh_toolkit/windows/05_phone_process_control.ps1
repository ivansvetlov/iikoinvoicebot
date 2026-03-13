param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status",
    [ValidateSet("all", "backend", "worker", "bot")]
    [string]$Target = "all",
    [string]$ProjectPath = "C:\Users\MiBookPro\PycharmProjects\PythonProject"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectPath)) {
    throw "ProjectPath not found: $ProjectPath"
}

$python = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python runtime not found: $python"
}

$logsDir = Join-Path $ProjectPath "logs"
$pidDir = Join-Path $ProjectPath "tmp\phonectl"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
New-Item -ItemType Directory -Path $pidDir -Force | Out-Null

$components = @{
    backend = @{
        pid   = "backend.pid"
        match = "app\.entrypoints\.main:app"
        args  = @("-m", "uvicorn", "app.entrypoints.main:app", "--host", "127.0.0.1", "--port", "8000")
    }
    worker = @{
        pid   = "worker.pid"
        match = "app\.entrypoints\.worker"
        args  = @("-m", "app.entrypoints.worker")
    }
    bot = @{
        pid   = "bot.pid"
        match = "app\.entrypoints\.bot"
        args  = @("-m", "app.entrypoints.bot")
    }
}

function Get-Targets([string]$target) {
    if ($target -eq "all") {
        return @("backend", "worker", "bot")
    }
    return @($target)
}

function Get-PidPath([string]$name) {
    return Join-Path $pidDir $components[$name].pid
}

function Save-Pid([string]$name, [int]$procId) {
    Set-Content -LiteralPath (Get-PidPath $name) -Value "$procId" -Encoding ascii
}

function Remove-Pid([string]$name) {
    $path = Get-PidPath $name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

function Get-ProcByPidFile([string]$name) {
    $path = Get-PidPath $name
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    $raw = (Get-Content -LiteralPath $path -Raw).Trim()
    $procId = 0
    if (-not [int]::TryParse($raw, [ref]$procId)) {
        Remove-Pid $name
        return $null
    }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Remove-Pid $name
        return $null
    }
    return $proc
}

function Find-ProcByMatch([string]$name) {
    $pattern = $components[$name].match
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine -match $pattern) {
            $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                return $proc
            }
        }
    }
    return $null
}

function Resolve-Proc([string]$name) {
    $proc = Get-ProcByPidFile $name
    if ($null -ne $proc) {
        return $proc
    }
    $proc = Find-ProcByMatch $name
    if ($null -ne $proc) {
        Save-Pid $name $proc.Id
        return $proc
    }
    return $null
}

function Start-Component([string]$name) {
    $proc = Resolve-Proc $name
    if ($null -ne $proc) {
        Write-Host "[running] $name pid=$($proc.Id)"
        return
    }

    $stdout = Join-Path $logsDir "$name.out.log"
    $stderr = Join-Path $logsDir "$name.err.log"
    $args = $components[$name].args

    $started = Start-Process `
        -FilePath $python `
        -ArgumentList $args `
        -WorkingDirectory $ProjectPath `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Milliseconds 600
    Save-Pid $name $started.Id
    Write-Host "[started] $name pid=$($started.Id)"
}

function Stop-Component([string]$name) {
    $proc = Resolve-Proc $name
    if ($null -eq $proc) {
        Remove-Pid $name
        Write-Host "[stopped] $name"
        return
    }

    $procId = $proc.Id
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Remove-Pid $name
    Write-Host "[stopped] $name pid=$procId"
}

function Status-Component([string]$name) {
    $proc = Resolve-Proc $name
    if ($null -eq $proc) {
        Write-Host "[down] $name"
        return
    }
    Write-Host "[up] $name pid=$($proc.Id)"
}

$targets = Get-Targets $Target
foreach ($name in $targets) {
    switch ($Action) {
        "start" { Start-Component $name }
        "stop" { Stop-Component $name }
        "restart" {
            Stop-Component $name
            Start-Component $name
        }
        "status" { Status-Component $name }
    }
}
