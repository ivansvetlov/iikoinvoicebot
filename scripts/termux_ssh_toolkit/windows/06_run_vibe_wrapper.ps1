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
$ProgressPreference = "SilentlyContinue"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
chcp 65001 > $null

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

function Test-IsLabsModel([string]$name) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        return $false
    }
    return $name -match '^(?i)labs[-/]'
}

function Get-AllowLabsModels {
    $raw = if ([string]::IsNullOrWhiteSpace($env:WVIBE_ALLOW_LABS)) {
        [Environment]::GetEnvironmentVariable("WVIBE_ALLOW_LABS", "User")
    } else {
        $env:WVIBE_ALLOW_LABS
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $false
    }
    switch -Regex ($raw.Trim()) {
        "^(?i:1|true|yes|on)$" { return $true }
        default { return $false }
    }
}

function Resolve-FallbackModel {
    $fallback = if ([string]::IsNullOrWhiteSpace($env:WVIBE_API_FALLBACK_MODEL)) {
        [Environment]::GetEnvironmentVariable("WVIBE_API_FALLBACK_MODEL", "User")
    } else {
        $env:WVIBE_API_FALLBACK_MODEL
    }
    if ([string]::IsNullOrWhiteSpace($fallback)) {
        $fallback = "mistral-small-latest"
    }
    if ((Test-IsLabsModel $fallback) -and -not (Get-AllowLabsModels)) {
        Write-Host "[warn] WVIBE_API_FALLBACK_MODEL '$fallback' points to Labs model; using 'mistral-small-latest'."
        return "mistral-small-latest"
    }
    return $fallback
}

function Get-ActiveModelName {
    $defaultModel = Resolve-FallbackModel
    $cfgPath = Join-Path $env:USERPROFILE ".vibe\config.toml"
    if (Test-Path -LiteralPath $cfgPath) {
        $rawCfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8
        $m = [regex]::Match($rawCfg, '(?m)^\s*active_model\s*=\s*"([^"]+)"\s*$')
        if ($m.Success) {
            $name = $m.Groups[1].Value
            if ($name -eq "devstral-2") {
                return $defaultModel
            }
            if ((Test-IsLabsModel $name) -and -not (Get-AllowLabsModels)) {
                return $defaultModel
            }
            return $name
        }
    }
    return $defaultModel
}

function Ensure-CompatibleActiveModel {
    $cfgPath = Join-Path $env:USERPROFILE ".vibe\config.toml"
    if (-not (Test-Path -LiteralPath $cfgPath)) {
        return
    }

    $rawCfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8
    if (-not $rawCfg) {
        return
    }

    $m = [regex]::Match($rawCfg, '(?m)^\s*active_model\s*=\s*"([^"]+)"\s*$')
    if (-not $m.Success) {
        return
    }

    $current = $m.Groups[1].Value
    $fallback = Resolve-FallbackModel
    $legacyInvalid = @("devstral-2")
    if ($legacyInvalid -contains $current) {
        # Legacy alias in config should always be migrated.
    } elseif ((Test-IsLabsModel $current) -and -not (Get-AllowLabsModels)) {
        # Labs model is configured, but current policy disallows Labs.
    } else {
        return
    }

    $updated = [regex]::Replace(
        $rawCfg,
        '(?m)^(\s*active_model\s*=\s*")[^"]+(".*)$',
        '${1}' + $fallback + '${2}',
        1
    )
    if ($updated -ne $rawCfg) {
        [System.IO.File]::WriteAllText($cfgPath, $updated, [System.Text.UTF8Encoding]::new($false))
        Write-Host "[info] active_model '$current' is legacy/invalid; switched to '$fallback' in $cfgPath"
    }
}

Ensure-CompatibleActiveModel

function Get-WebErrorBody([System.Exception]$exception) {
    if ($null -eq $exception) {
        return ""
    }
    $response = $null
    if ($exception.PSObject.Properties.Match("Response").Count -gt 0) {
        $response = $exception.Response
    }
    if ($null -eq $response) {
        return ""
    }
    try {
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) {
            return ""
        }
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Close()
            $stream.Close()
        }
    } catch {
        return ""
    }
}

function Invoke-DirectApiAsk([string]$promptText) {
    if ([string]::IsNullOrWhiteSpace($promptText)) {
        throw "Task is required for api_ask mode."
    }
    # Defensive sanitation for JSON body stability.
    $promptText = $promptText -replace "`0", ""
    if ($promptText.Length -gt 12000) {
        $promptText = $promptText.Substring(0, 12000)
    }

    $apiKey = $env:MISTRAL_API_KEY
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        $apiKey = [Environment]::GetEnvironmentVariable("MISTRAL_API_KEY", "User")
    }
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "MISTRAL_API_KEY is not set."
    }

    $primaryModel = Get-ActiveModelName
    $fallbackModel = Resolve-FallbackModel
    $models = @()
    foreach ($m in @($primaryModel, $fallbackModel)) {
        if (-not [string]::IsNullOrWhiteSpace($m) -and ($models -notcontains $m)) {
            $models += $m
        }
    }
    if ($models -notcontains "mistral-small-latest") {
        # Keep a stable non-Labs model as universal fallback.
        $models += "mistral-small-latest"
    }
    if ($models.Count -eq 0) {
        $models = @("mistral-small-latest")
    }

    $lastError = ""
    foreach ($modelName in $models) {
        try {
            $bodyObj = @{
                model      = $modelName
                messages   = @(@{ role = "user"; content = $promptText })
                max_tokens = 512
            }
            $jsonBody = $bodyObj | ConvertTo-Json -Depth 6 -Compress
            $jsonUtf8 = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)
            $response = Invoke-RestMethod -Method Post -Uri "https://api.mistral.ai/v1/chat/completions" -Headers @{ Authorization = "Bearer $apiKey" } -Body $jsonUtf8 -ContentType "application/json; charset=utf-8" -TimeoutSec 45
            $answer = $response.choices[0].message.content
            if ($null -eq $answer) {
                $answer = ""
            }
            $answerText = [string]$answer
            $answerB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($answerText))
            Write-Output "__WVIBE_B64_BEGIN__"
            Write-Output $answerB64
            Write-Output "__WVIBE_B64_END__"
            if ($modelName -ne $primaryModel) {
                Write-Host "[info] api_ask succeeded with fallback model '$modelName'"
            }
            return
        } catch {
            $errBody = Get-WebErrorBody $_.Exception
            if ([string]::IsNullOrWhiteSpace($errBody)) {
                $lastError = "model '$modelName' failed: $($_.Exception.Message)"
            } else {
                $lastError = "model '$modelName' failed: $($_.Exception.Message)`n$errBody"
            }
            if ($modelName -ne $models[-1]) {
                Write-Host "[warn] api_ask failed for model '$modelName', trying fallback..."
            }
        }
    }

    throw "Invoke-DirectApiAsk failed. $lastError"
}

function Read-FileSnippet([string]$path, [int]$maxChars = 5000) {
    if (-not (Test-Path -LiteralPath $path)) {
        return ""
    }
    $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    if ($raw.Length -le $maxChars) {
        return $raw
    }
    return $raw.Substring(0, $maxChars)
}

function Build-ApiAskPrompt([string]$taskText, [switch]$NoBootstrap) {
    if ($NoBootstrap) {
        return $taskText
    }

    $startHere = Read-FileSnippet -path (Join-Path $ProjectPath "docs\START_HERE_NEW_CHAT.md")
    $todo = Read-FileSnippet -path (Join-Path $ProjectPath "docs\TODO.md")
    $arch = Read-FileSnippet -path (Join-Path $ProjectPath "docs\ARCHITECTURE.md")

    return @"
Use project context below to answer the user task.
Be concise and practical. If context is insufficient, ask up to 3 clarifying questions.

=== docs/START_HERE_NEW_CHAT.md (snippet) ===
$startHere

=== docs/TODO.md (snippet) ===
$todo

=== docs/ARCHITECTURE.md (snippet) ===
$arch

=== User task ===
$taskText
"@
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
    $apiPrompt = Build-ApiAskPrompt -taskText $Task -NoBootstrap:$SkipBootstrap
    Invoke-DirectApiAsk -promptText $apiPrompt
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
