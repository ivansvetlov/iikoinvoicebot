param(
    [string]$ProjectPath = "C:\Users\MiBookPro\PycharmProjects\PythonProject",
    [string]$UvBinPath = "C:\Users\MiBookPro\.local\bin",
    [string]$Task = "",
    [string]$TaskBase64 = "",
    [ValidateSet("start", "reconnect", "mcp_cmd", "ask", "api_ask", "stop", "doctor")]
    [string]$Mode = "start",
    [switch]$SkipBootstrap,
    [switch]$ForceCleanup,
    [switch]$EnableMcp,
    [int]$AskMaxTurns = 8
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
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if ([string]::IsNullOrWhiteSpace($env:MISTRAL_API_KEY)) {
    $env:MISTRAL_API_KEY = [Environment]::GetEnvironmentVariable("MISTRAL_API_KEY", "User")
}

if ([string]::IsNullOrWhiteSpace($Task) -and -not [string]::IsNullOrWhiteSpace($TaskBase64)) {
    try {
        $Task = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($TaskBase64))
    } catch {
        throw "TaskBase64 is not valid Base64 UTF-8 text."
    }
}

$agentName = "phone-wrapper"
$agentFile = Join-Path $ProjectPath ".vibe\agents\phone-wrapper.toml"
$agentArgs = @()
if (Test-Path -LiteralPath $agentFile) {
    $agentArgs = @("--agent", $agentName)
}

function Set-McpBridgeEnv {
    $vibePython = Join-Path $env:APPDATA "uv\tools\mistral-vibe\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $vibePython)) {
        $vibePython = "python"
    }

    $serverScript = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\mcp\termux_bridge_mcp.py"
    if (-not (Test-Path -LiteralPath $serverScript)) {
        return
    }

    $mcpServers = @(
        @{
            transport           = "stdio"
            name                = "termux_bridge"
            command             = @($vibePython, $serverScript)
            args                = @()
            prompt              = "Bridge for executing host commands and returning stdout/stderr/exit_code."
            startup_timeout_sec = 15
            tool_timeout_sec    = 180
            sampling_enabled    = $false
        }
    )

    $env:VIBE_MCP_SERVERS = (ConvertTo-Json -InputObject $mcpServers -Compress -Depth 8)
}

if ($Mode -eq "mcp_cmd" -or $EnableMcp) {
    Set-McpBridgeEnv
} else {
    Remove-Item Env:VIBE_MCP_SERVERS -ErrorAction SilentlyContinue
}

function Get-VibeProcessInfo {
    $rows = @()
    $raw = @()

    foreach ($name in @("vibe.exe", "vibe-acp.exe")) {
        $raw += Get-CimInstance Win32_Process -Filter "Name = '$name'" -ErrorAction SilentlyContinue
    }

    $py = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $py) {
        if ($p.CommandLine -and $p.CommandLine -match "termux_bridge_mcp\.py") {
            $raw += $p
        }
    }

    $seen = @{}
    foreach ($p in $raw) {
        if ($seen.ContainsKey($p.ProcessId)) {
            continue
        }
        $seen[$p.ProcessId] = $true

        $owner = ""
        try {
            $ownerInfo = Invoke-CimMethod -InputObject $p -MethodName GetOwner -ErrorAction Stop
            if ($ownerInfo.User) {
                if ($ownerInfo.Domain) {
                    $owner = "$($ownerInfo.Domain)\$($ownerInfo.User)"
                } else {
                    $owner = "$($ownerInfo.User)"
                }
            }
        } catch {
            $owner = ""
        }

        $sessionId = [int]$p.SessionId
        $isCurrentUser = $false
        if ($owner) {
            $ownerUser = ($owner -split "\\")[-1]
            $isCurrentUser = $ownerUser -ieq $env:USERNAME
        } elseif ($sessionId -ne 0) {
            # If owner lookup is unavailable but process is not in Services session,
            # treat it as current interactive user scope.
            $isCurrentUser = $true
        }

        $cmdLine = ""
        if ($p.CommandLine) {
            $cmdLine = "$($p.CommandLine)"
        }

        $rows += [PSCustomObject]@{
            Pid           = [int]$p.ProcessId
            Name          = [string]$p.Name
            SessionId     = [int]$sessionId
            Owner         = [string]$owner
            IsCurrentUser = [bool]$isCurrentUser
            CommandLine   = [string]$cmdLine
        }
    }

    return @($rows | Sort-Object Pid)
}

function Show-VibeProcesses([object[]]$Items) {
    if (-not $Items -or $Items.Count -eq 0) {
        Write-Host "[ok] no vibe-related processes found."
        return
    }

    Write-Host "[info] vibe-related processes:"
    foreach ($item in $Items) {
        $owner = if ([string]::IsNullOrWhiteSpace($item.Owner)) { "<unknown>" } else { $item.Owner }
        Write-Host (" - pid={0} name={1} session={2} owner={3}" -f $item.Pid, $item.Name, $item.SessionId, $owner)
    }
}

function Stop-VibeProcesses([switch]$CurrentUserOnly) {
    $items = Get-VibeProcessInfo
    if ($CurrentUserOnly) {
        $items = @($items | Where-Object { $_.IsCurrentUser })
    }

    if (-not $items -or $items.Count -eq 0) {
        Write-Host "[ok] no matching vibe processes to stop."
        return 0
    }

    $failed = 0
    foreach ($item in $items) {
        try {
            Stop-Process -Id $item.Pid -Force -ErrorAction Stop
            Write-Host ("[stopped] pid={0} name={1}" -f $item.Pid, $item.Name)
        } catch {
            $failed++
            Write-Host ("[warn] failed to stop pid={0} name={1}: {2}" -f $item.Pid, $item.Name, $_.Exception.Message)
        }
    }

    if ($failed -gt 0) {
        Write-Host "[hint] Some processes were not stoppable from this session."
        Write-Host "[hint] Run elevated PowerShell and execute: Get-Process vibe,vibe-acp -ErrorAction SilentlyContinue | Stop-Process -Force"
        return 1
    }

    return 0
}

function Show-LockFiles {
    $vibeDir = Join-Path $ProjectPath ".vibe"
    if (-not (Test-Path -LiteralPath $vibeDir)) {
        Write-Host "[info] .vibe directory not found."
        return
    }

    $locks = Get-ChildItem -LiteralPath $vibeDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*.lock" }
    if (-not $locks -or $locks.Count -eq 0) {
        Write-Host "[ok] no lock files under .vibe"
        return
    }

    Write-Host "[info] lock files under .vibe:"
    foreach ($lf in $locks) {
        Write-Host (" - {0}" -f $lf.FullName)
    }
}

if ($Mode -eq "doctor") {
    Write-Host "[doctor] checking vibe process state..."
    $all = Get-VibeProcessInfo
    Show-VibeProcesses -Items $all
    Show-LockFiles
    exit 0
}

if ($Mode -eq "stop") {
    $stopCode = Stop-VibeProcesses -CurrentUserOnly
    exit $stopCode
}

if ($ForceCleanup) {
    $stopCode = Stop-VibeProcesses -CurrentUserOnly
    if ($stopCode -ne 0) {
        exit $stopCode
    }
}

if (-not $ForceCleanup) {
    $active = @(Get-VibeProcessInfo | Where-Object { $_.IsCurrentUser -and ($_.Name -in @("vibe.exe", "vibe-acp.exe")) })
    if ($active.Count -gt 0) {
        Write-Host "[blocked] vibe is already running for this user."
        Show-VibeProcesses -Items $active
        Write-Host "[next] run: wvibe stop"
        Write-Host "[next] or force cleanup: wvibe --force"
        exit 10
    }
}

if ($Mode -eq "reconnect") {
    & $vibeExe -c @agentArgs
    exit $LASTEXITCODE
}

if ($Mode -eq "mcp_cmd") {
    if ([string]::IsNullOrWhiteSpace($Task)) {
        throw "Task is required for mcp_cmd mode."
    }

    $mcpPrompt = @"
Run the user command via MCP tool `termux_bridge_run_command`.
Rules:
1) Call the tool exactly once.
2) Pass the exact user command text to `command` without edits.
3) Return only:
   - exit_code
   - stdout
   - stderr
No extra analysis.

User command:
$Task
"@

    & $vibeExe @agentArgs -p $mcpPrompt --max-turns 6 --output text
    exit $LASTEXITCODE
}

function Get-BootstrapPrompt {
    return @"
Bootstrap project context first:
1) Read files:
   - docs/START_HERE_NEW_CHAT.md
   - docs/AGENT_HANDOFF.md
   - docs/TODO.md
   - docs/ARCHITECTURE.md
   - docs/README.md
   - VIBE.md
2) Then provide a short status:
   - done
   - in progress
   - next
   - risks/blockers
3) If the user asks to run an exact terminal command, use MCP tool
   `termux_bridge_run_command` and return actual output.
4) Then continue with the user task.
"@
}

function Get-AskBootstrapPrompt {
    return @"
Quick bootstrap:
1) Read only:
   - docs/START_HERE_NEW_CHAT.md
   - docs/TODO.md
2) Provide concise status:
   - done
   - in progress
   - next
   - risks/blockers
"@
}

function Get-ActiveModelName {
    $cfgPath = Join-Path $env:USERPROFILE ".vibe\config.toml"
    if (Test-Path -LiteralPath $cfgPath) {
        $rawCfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8
        $m = [regex]::Match($rawCfg, '(?m)^\s*active_model\s*=\s*"([^"]+)"\s*$')
        if ($m.Success) {
            $name = $m.Groups[1].Value
            if ($name -eq "devstral-2") {
                return "labs-leanstral-2603"
            }
            return $name
        }
    }
    return "labs-leanstral-2603"
}

function Invoke-DirectApiAsk([string]$promptText) {
    if ([string]::IsNullOrWhiteSpace($promptText)) {
        throw "Task is required for api_ask mode."
    }

    $apiKey = $env:MISTRAL_API_KEY
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        $apiKey = [Environment]::GetEnvironmentVariable("MISTRAL_API_KEY", "User")
    }
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "MISTRAL_API_KEY is not set."
    }

    $modelName = Get-ActiveModelName
    $bodyObj = @{
        model      = $modelName
        messages   = @(@{ role = "user"; content = $promptText })
        max_tokens = 512
    }
    $jsonBody = $bodyObj | ConvertTo-Json -Depth 6
    $response = Invoke-RestMethod -Method Post -Uri "https://api.mistral.ai/v1/chat/completions" -Headers @{ Authorization = "Bearer $apiKey" } -Body $jsonBody -ContentType "application/json" -TimeoutSec 45
    $answer = $response.choices[0].message.content
    if ($null -eq $answer) {
        $answer = ""
    }
    Write-Output "$answer"
}

if ($Mode -eq "ask") {
    if ([string]::IsNullOrWhiteSpace($Task)) {
        $Task = "Read project context files and give short status: done/in progress/next/risks."
    }

    if ($SkipBootstrap) {
        $askPrompt = $Task
    } else {
        $bootstrap = Get-AskBootstrapPrompt
        $askPrompt = @"
$bootstrap

User task:
$Task
"@
    }

    if ($AskMaxTurns -lt 1) { $AskMaxTurns = 1 }
    if ($AskMaxTurns -gt 24) { $AskMaxTurns = 24 }
    & $vibeExe @agentArgs -p $askPrompt --max-turns $AskMaxTurns --output text
    exit $LASTEXITCODE
}

if ($Mode -eq "api_ask") {
    if ([string]::IsNullOrWhiteSpace($Task)) {
        $Task = "Reply exactly: API_OK"
    }
    Invoke-DirectApiAsk -promptText $Task
    exit 0
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

User task:
$Task
"@
}

& $vibeExe @agentArgs $wrappedPrompt
exit $LASTEXITCODE
