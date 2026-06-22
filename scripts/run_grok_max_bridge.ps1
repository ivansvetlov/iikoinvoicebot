# Grok ↔ MAX bridge (feature/channel-max). Requires GROK_MAX_BRIDGE_TOKEN in .env.
Set-Location $PSScriptRoot\..
$env:PYTHONUNBUFFERED = "1"
.\.venv\Scripts\python.exe -m experiments.grok_max_bridge
