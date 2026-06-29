# Print dashboard URLs: local, LAN, Tailscale, Cloudflare (if configured).
param(
    [int]$Port = 8765,
    [string]$Rel = "docs/assets/project-dashboard.html"
)

$ErrorActionPreference = "SilentlyContinue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "Dashboard paths ($root)"
Write-Host "  Local:    http://127.0.0.1:$Port/$Rel"

try {
    $py = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $lan = & $py -c "from experiments.grok_telegram_bridge.dashboard_hub import local_lan_ip; print(local_lan_ip() or '')" 2>$null
    if ($lan) { Write-Host "  LAN:      http://${lan}:$Port/$Rel" }
    $ts = & $py -c "from experiments.grok_telegram_bridge.dashboard_hub import tailscale_ip; print(tailscale_ip() or '')" 2>$null
    if ($ts) {
        Write-Host "  Tailscale: http://${ts}:$Port/$Rel"
    } else {
        $svc = Get-Service Tailscale -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne "Running") {
            Write-Host "  Tailscale: (service stopped - start Tailscale and sign in)"
        } else {
            Write-Host "  Tailscale: (not connected - run: tailscale up)"
        }
    }
} catch {
    Write-Host "  LAN/Tailscale: (python helper failed)"
}

$cf = $env:CLOUDFLARE_DASHBOARD_URL
if (-not $cf) {
    $cfg = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    if (Test-Path $cfg) {
        $m = Select-String -Path $cfg -Pattern 'hostname:\s*(\S+)' | Select-Object -First 1
        if ($m) { $cf = "https://$($m.Matches.Groups[1].Value)/$Rel" }
    }
}
if ($cf) {
    Write-Host "  Cloudflare: $cf"
} else {
    Write-Host "  Cloudflare: (not configured - see config/cloudflared/config.example.yml)"
}

Write-Host ""
Write-Host "Start server: .\.venv\Scripts\python.exe scripts\serve_project_dashboard.py"
