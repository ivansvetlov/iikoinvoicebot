param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin",
    [switch]$WithBootstrap,
    [string]$Task = "",
    [int]$AskMaxTurns = 8,
    [switch]$EnableMcp
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

$wrapperPath = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\06_run_vibe_wrapper.ps1"
if (-not (Test-Path -LiteralPath $wrapperPath)) {
    throw "Wrapper script not found: $wrapperPath"
}

function Normalize-AskBackend([string]$raw) {
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return "api"
    }
    switch -Regex ($raw.Trim().ToLowerInvariant()) {
        "^(cli|ask)$" { return "cli" }
        "^(api|api_ask)$" { return "api" }
        default { return "api" }
    }
}

function Decode-ApiAskOutput([string]$rawText) {
    if ([string]::IsNullOrWhiteSpace($rawText)) {
        return ""
    }
    $m = [regex]::Match($rawText, '(?s)__WVIBE_B64_BEGIN__\s*(?<b64>[A-Za-z0-9+/=\r\n]+?)\s*__WVIBE_B64_END__')
    if (-not $m.Success) {
        return $rawText
    }
    $b64 = ($m.Groups['b64'].Value -replace '\s', '')
    if ([string]::IsNullOrWhiteSpace($b64)) {
        return ""
    }
    try {
        $bytes = [Convert]::FromBase64String($b64)
        return [System.Text.Encoding]::UTF8.GetString($bytes)
    } catch {
        return $rawText
    }
}

function Get-ToolkitAliases {
    $toolkitPath = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\shared\toolkit_functions.sh"
    if (-not (Test-Path -LiteralPath $toolkitPath)) {
        return @()
    }

    $raw = Get-Content -LiteralPath $toolkitPath -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @()
    }

    $seen = @{}
    $items = New-Object System.Collections.Generic.List[string]
    $matches = [regex]::Matches($raw, '(?m)^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{')
    foreach ($m in $matches) {
        $name = $m.Groups[1].Value
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if ($name.StartsWith("_")) { continue }
        if (-not $name.StartsWith("w")) { continue }
        if ($seen.ContainsKey($name)) { continue }
        $seen[$name] = $true
        $items.Add($name) | Out-Null
    }

    if ($items.Count -eq 0) {
        return @()
    }
    return @($items | Sort-Object)
}

function Show-ToolkitAliases {
    $aliases = Get-ToolkitAliases
    if (-not $aliases -or $aliases.Count -eq 0) {
        Write-Host "[warn] alias list not found."
        return
    }
    Write-Host "Termux aliases:"
    foreach ($a in $aliases) {
        Write-Output $a
    }
}

function Test-IsAliasQuery([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $false
    }
    if ($text -match '(?i)\balias(es)?\b') { return $true }
    if ($text -match 'алиас') { return $true }
    if ($text -match '(?i)\btermux\b.*\bcommands?\b') { return $true }
    if ($text -match 'список\s+команд') { return $true }
    if ($text -match 'какие\s+команд') { return $true }
    return $false
}

function Show-LocalHelp {
    @"
Легкая оболочка Vibe:
  Вводи задачу одной строкой и жми Enter.
  Команды:
    /help        показать эту справку
    /doctor      проверить состояние wrapper
    /reconnect   продолжить последнюю сессию
    /mcp on|off  включить/выключить MCP режим
    /mcpcmd ...  выполнить точную команду через MCP
    /backend api|cli  переключить backend для ask-запросов
    /aliases     показать текущий список w* алиасов (без LLM)
    /turns N     поставить лимит turn'ов для ask (1..24)
    /bootstrap   включить bootstrap на следующий запрос
    /noboot      выключить bootstrap (по умолчанию)
    /exit        выйти
"@ | Out-Host
}

$useBootstrap = $WithBootstrap.IsPresent
$useMcp = $EnableMcp.IsPresent
$askBackend = Normalize-AskBackend $env:WVIBE_SHELL_ASK_BACKEND
if ($AskMaxTurns -lt 1) { $AskMaxTurns = 1 }
if ($AskMaxTurns -gt 24) { $AskMaxTurns = 24 }

function Invoke-Ask([string]$text) {
    # MCP ask path currently requires CLI backend.
    if ($useMcp -or $askBackend -eq "cli") {
        if ($useBootstrap) {
            if ($useMcp) {
                & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --mcp --max-turns $AskMaxTurns $text
            } else {
                & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --max-turns $AskMaxTurns $text
            }
        } else {
            if ($useMcp) {
                & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --no-bootstrap --mcp --max-turns $AskMaxTurns $text
            } else {
                & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath ask --no-bootstrap --max-turns $AskMaxTurns $text
            }
        }
        return
    }

    $apiArgs = @{
        ProjectPath = $ProjectPath
        UvBinPath   = $UvBinPath
        Mode        = "api_ask"
        Task        = $text
    }
    $needsContext = $useBootstrap -or (Test-IsAliasQuery -text $text)
    if (-not $needsContext) {
        $apiArgs.SkipBootstrap = $true
    }
    $raw = & $wrapperPath @apiArgs | Out-String
    $decoded = Decode-ApiAskOutput -rawText $raw
    if (-not [string]::IsNullOrWhiteSpace($decoded)) {
        $clean = $decoded.TrimEnd("`r", "`n")
        if (-not [string]::IsNullOrWhiteSpace($clean)) {
            Write-Output $clean
        }
    }
}

if (-not [string]::IsNullOrWhiteSpace($Task)) {
    if ($Task.Trim() -match '^\/aliases$') {
        Show-ToolkitAliases
        exit 0
    }
    Invoke-Ask -text $Task
    exit $LASTEXITCODE
}

Write-Host "Легкая оболочка Vibe запущена."
if ($useBootstrap) {
    Write-Host "Режим: bootstrap включен."
} else {
    Write-Host "Режим: без bootstrap."
}
if ($useMcp) {
    Write-Host "MCP: on"
} else {
    Write-Host "MCP: off"
}
Write-Host "ask backend: $askBackend"
Write-Host "ask turns: $AskMaxTurns"
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
        "^\/mcp\s+on$" {
            $useMcp = $true
            Write-Host "mcp: on"
            continue
        }
        "^\/mcp\s+off$" {
            $useMcp = $false
            Write-Host "mcp: off"
            continue
        }
        "^\/backend\s+(api|cli)$" {
            $askBackend = $matches[1].ToLowerInvariant()
            Write-Host "ask backend: $askBackend"
            continue
        }
        "^\/aliases$" {
            Show-ToolkitAliases
            continue
        }
        "^\/mcpcmd\s+(.+)$" {
            & $shimPath -ProjectPath $ProjectPath -UvBinPath $UvBinPath mcp $matches[1]
            continue
        }
        "^\/turns\s+(\d+)$" {
            $t = [int]$matches[1]
            if ($t -lt 1) { $t = 1 }
            if ($t -gt 24) { $t = 24 }
            $AskMaxTurns = $t
            Write-Host "ask turns: $AskMaxTurns"
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
                Invoke-Ask -text $cmd
            } catch {
                Write-Host "[error] $($_.Exception.Message)"
            }
        }
    }
}

Write-Host "Выход из легкой оболочки Vibe."
