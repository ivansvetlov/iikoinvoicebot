# Invoice bot on MAX (feature/channel-max). Requires MAX_INVOICE_BOT_TOKEN in .env.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& "$root\.venv\Scripts\python.exe" -m experiments.max_invoice_bot
