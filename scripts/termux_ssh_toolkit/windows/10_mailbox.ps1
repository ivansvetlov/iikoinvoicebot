param(
    [ValidateSet("ensure", "plan", "status", "list", "digest", "show", "termux", "reply", "resolve", "prompt", "handoff")]
    [string]$Action = "status",
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$Text = "",
    [string]$Source = "termux",
    [string[]]$Items = @()
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

$mailRoot = Join-Path $ProjectPath "ops\mailbox"
$inboxDir = Join-Path $mailRoot "inbox"
$processedDir = Join-Path $mailRoot "processed"
$outboxDir = Join-Path $mailRoot "outbox"
$forCodexPath = Join-Path $mailRoot "for_codex.md"
$forTermuxPath = Join-Path $mailRoot "for_termux.md"

function Ensure-Layout {
    New-Item -ItemType Directory -Path $mailRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $inboxDir -Force | Out-Null
    New-Item -ItemType Directory -Path $processedDir -Force | Out-Null
    New-Item -ItemType Directory -Path $outboxDir -Force | Out-Null

    if (-not (Test-Path -LiteralPath $forCodexPath)) {
        [System.IO.File]::WriteAllText(
            $forCodexPath,
            "# Codex Mailbox`n`nПока нет задач.`n",
            [System.Text.UTF8Encoding]::new($true)
        )
    }
    if (-not (Test-Path -LiteralPath $forTermuxPath)) {
        [System.IO.File]::WriteAllText(
            $forTermuxPath,
            "# Termux Mailbox`n`nПока нет ответов.`n",
            [System.Text.UTF8Encoding]::new($true)
        )
    }
}

function New-PlanItem([string]$taskText, [string]$src) {
    if ([string]::IsNullOrWhiteSpace($taskText)) {
        throw "Text is required for plan action."
    }

    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $safeSrc = ($src -replace "[^a-zA-Z0-9_-]", "_")
    if ([string]::IsNullOrWhiteSpace($safeSrc)) {
        $safeSrc = "termux"
    }
    $name = "$stamp-$safeSrc.md"
    $path = Join-Path $inboxDir $name
    $created = (Get-Date).ToString("s")

    $body = @"
# Plan Item

- created_at: $created
- source: $safeSrc
- status: new

## Task
$taskText
"@

    [System.IO.File]::WriteAllText($path, $body, [System.Text.UTF8Encoding]::new($true))
    Write-Output "[ok] created: $path"
}

function Show-Status {
    $inboxCount = @(Get-ChildItem -LiteralPath $inboxDir -File -Filter *.md -ErrorAction SilentlyContinue).Count
    $processedCount = @(Get-ChildItem -LiteralPath $processedDir -File -Filter *.md -ErrorAction SilentlyContinue).Count
    $outboxCount = @(Get-ChildItem -LiteralPath $outboxDir -File -Filter *.md -ErrorAction SilentlyContinue).Count

    Write-Output "mailbox: $mailRoot"
    Write-Output "inbox: $inboxCount"
    Write-Output "processed: $processedCount"
    Write-Output "outbox: $outboxCount"
    Write-Output "for_codex: $forCodexPath"
    Write-Output "for_termux: $forTermuxPath"
}

function List-Inbox {
    $items = Get-ChildItem -LiteralPath $inboxDir -File -Filter *.md -ErrorAction SilentlyContinue | Sort-Object LastWriteTime
    if (-not $items -or $items.Count -eq 0) {
        Write-Output "[ok] inbox is empty."
        return
    }
    foreach ($it in $items) {
        $ts = $it.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
        Write-Output "$ts  $($it.Name)"
    }
}

function Build-Digest([switch]$Quiet) {
    $items = Get-ChildItem -LiteralPath $inboxDir -File -Filter *.md -ErrorAction SilentlyContinue | Sort-Object LastWriteTime
    $now = (Get-Date).ToString("s")

    if (-not $items -or $items.Count -eq 0) {
        $empty = @"
# Codex Mailbox

Generated: $now

Новых задач нет.
"@
        [System.IO.File]::WriteAllText($forCodexPath, $empty, [System.Text.UTF8Encoding]::new($true))
        if (-not $Quiet) {
            Write-Output "[ok] digest updated: $forCodexPath"
        }
        return
    }

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# Codex Mailbox")
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("Generated: $now")
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("## Inbox Files")
    foreach ($it in $items) {
        [void]$sb.AppendLine("- $($it.Name)")
    }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("## Tasks")
    [void]$sb.AppendLine()
    foreach ($it in $items) {
        $content = Get-Content -LiteralPath $it.FullName -Raw -Encoding UTF8
        [void]$sb.AppendLine("### $($it.Name)")
        [void]$sb.AppendLine($content.TrimEnd())
        [void]$sb.AppendLine()
    }
    [void]$sb.AppendLine("## Instruction")
    [void]$sb.AppendLine("Обработай задачи выше по приоритету и подготовь ответ для пользователя.")

    [System.IO.File]::WriteAllText($forCodexPath, $sb.ToString(), [System.Text.UTF8Encoding]::new($true))
    if (-not $Quiet) {
        Write-Output "[ok] digest updated: $forCodexPath"
    }
}

function Show-ForCodex {
    if (-not (Test-Path -LiteralPath $forCodexPath)) {
        Write-Output "[warn] file not found: $forCodexPath"
        return
    }
    Get-Content -LiteralPath $forCodexPath -Raw -Encoding UTF8 | Write-Output
}

function Show-ForTermux {
    if (-not (Test-Path -LiteralPath $forTermuxPath)) {
        Write-Output "[warn] file not found: $forTermuxPath"
        return
    }
    Get-Content -LiteralPath $forTermuxPath -Raw -Encoding UTF8 | Write-Output
}

function Publish-ForTermux([string]$replyText, [string]$src) {
    if ([string]::IsNullOrWhiteSpace($replyText)) {
        throw "Text is required for reply action."
    }

    $safeSrc = ($src -replace "[^a-zA-Z0-9_-]", "_")
    if ([string]::IsNullOrWhiteSpace($safeSrc)) {
        $safeSrc = "windows"
    }

    $now = (Get-Date).ToString("s")
    $body = @"
# Termux Mailbox

Generated: $now
Source: $safeSrc

$replyText
"@
    [System.IO.File]::WriteAllText($forTermuxPath, $body, [System.Text.UTF8Encoding]::new($true))

    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $logPath = Join-Path $outboxDir "$stamp-$safeSrc-termux.md"
    [System.IO.File]::WriteAllText($logPath, $body, [System.Text.UTF8Encoding]::new($true))

    Write-Output "[ok] termux reply updated: $forTermuxPath"
    Write-Output "[ok] outbox log: $logPath"
}

function Build-CodexPrompt {
    if (-not (Test-Path -LiteralPath $forCodexPath)) {
        Build-Digest -Quiet
    }

    return @"
Прочитай файл ops/mailbox/for_codex.md и выполни задачи из него.
Если данных недостаточно, задай до 3 уточняющих вопросов.
В ответе: сначала действия и изменения, затем коротко риски и следующий шаг.
"@.Trim()
}

function Handoff-Codex {
    Build-Digest -Quiet
    $prompt = Build-CodexPrompt
    $promptPath = Join-Path $outboxDir "codex_prompt_latest.txt"
    [System.IO.File]::WriteAllText($promptPath, $prompt, [System.Text.UTF8Encoding]::new($true))
    Write-Output $prompt
}

function Resolve-Items([string[]]$names) {
    if (-not $names -or $names.Count -eq 0) {
        throw "resolve action expects one or more file names from inbox."
    }

    foreach ($n in $names) {
        $src = Join-Path $inboxDir $n
        if (-not (Test-Path -LiteralPath $src)) {
            Write-Output "[skip] not found: $n"
            continue
        }
        $dst = Join-Path $processedDir $n
        Move-Item -LiteralPath $src -Destination $dst -Force
        Write-Output "[ok] moved: $n -> processed"
    }
}

Ensure-Layout

switch ($Action) {
    "ensure" { Show-Status; break }
    "plan" { New-PlanItem -taskText $Text -src $Source; break }
    "status" { Show-Status; break }
    "list" { List-Inbox; break }
    "digest" { Build-Digest; break }
    "show" { Show-ForCodex; break }
    "termux" { Show-ForTermux; break }
    "reply" { Publish-ForTermux -replyText $Text -src $Source; break }
    "resolve" { Resolve-Items -names $Items; break }
    "prompt" { Build-CodexPrompt | Write-Output; break }
    "handoff" { Handoff-Codex; break }
}
