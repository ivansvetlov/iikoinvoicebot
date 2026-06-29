# Safe restart: only experiments.grok_max_bridge (not invoice bot / dev_run_all).
Set-Location $PSScriptRoot\..
.\.venv\Scripts\python.exe scripts\grok_bridge_ctl.py restart --bridge max
