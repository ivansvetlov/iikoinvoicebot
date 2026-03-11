param(
    [Parameter(Mandatory = $true)]
    [string]$Pattern,
    [string]$Path = "docs/iiko_server_docs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $Path)) {
    throw "Path not found: $Path"
}

Get-ChildItem -Path $Path -File -Recurse |
    Where-Object { $_.Extension -in @(".md", ".html", ".txt", ".json") } |
    Select-String -Pattern $Pattern -SimpleMatch |
    ForEach-Object {
        "{0}:{1}: {2}" -f $_.Path, $_.LineNumber, ($_.Line.Trim())
    }

