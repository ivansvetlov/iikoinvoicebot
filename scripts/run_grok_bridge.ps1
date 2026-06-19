# Grok ↔ Telegram bridge (exp track). Requires GROK_BRIDGE_BOT_TOKEN in .env.
Set-Location $PSScriptRoot\..
$env:PYTHONUNBUFFERED = "1"
.\.venv\Scripts\python.exe -m experiments.grok_telegram_bridge
