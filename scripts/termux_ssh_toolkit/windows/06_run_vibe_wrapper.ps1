param(
    [string]$ProjectPath = "C:\Users\MiBookPro\PycharmProjects\PythonProject",
    [string]$UvBinPath = "C:\Users\MiBookPro\.local\bin",
    [string]$Task = "",
    [ValidateSet("start", "reconnect", "mcp_cmd")]
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

    $env:VIBE_MCP_SERVERS = ($mcpServers | ConvertTo-Json -Compress -Depth 8)
}

Set-McpBridgeEnv

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

