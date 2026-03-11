param(
    [Parameter(Mandatory = $true)]
    [string]$Pattern,
    [string]$Path = "iiko_server_docs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) {
    $Path
} else {
    Join-Path $repoRoot $Path
}

if (-not (Test-Path $resolvedPath)) {
    throw "Path not found: $resolvedPath"
}

Get-ChildItem -Path $resolvedPath -File -Recurse |
    Where-Object { $_.Extension -in @(".md", ".html", ".txt", ".json") } |
    Select-String -Pattern $Pattern -SimpleMatch |
    ForEach-Object {
        "{0}:{1}: {2}" -f $_.Path, $_.LineNumber, ($_.Line.Trim())
    }
