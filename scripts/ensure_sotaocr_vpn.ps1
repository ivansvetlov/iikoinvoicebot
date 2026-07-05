# Ensure split-tunnel WireGuard is active (SotaOCR + api.openai.com via VPN).
# Run once as Administrator to install the tunnel service.
param(
    [string]$SplitConfig = "",
    [string]$FullConfig = "$env:USERPROFILE\Downloads\vpn188958.conf"
)

if (-not $SplitConfig) {
    if ($env:SOTAOCR_WG_CONFIG) {
        $SplitConfig = $env:SOTAOCR_WG_CONFIG
        if (-not [System.IO.Path]::IsPathRooted($SplitConfig)) {
            $repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
            $SplitConfig = Join-Path $repoRoot $SplitConfig
        }
    } else {
        $repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
        $SplitConfig = Join-Path $repoRoot "config\wireguard\vpn188958_split_sotaocr.conf"
    }
}

$ErrorActionPreference = 'Stop'
$WireGuardExe = 'C:\Program Files\WireGuard\wireguard.exe'
$SplitService = 'WireGuardTunnel$vpn188958_split_sotaocr'
$FullService = 'WireGuardTunnel$vpn188958'

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Ensure-SplitTunnelInstalled {
    if (-not (Test-Path $SplitConfig)) {
        throw "Split config not found: $SplitConfig"
    }
    if (-not (Test-Path $WireGuardExe)) {
        throw "WireGuard not installed: $WireGuardExe"
    }
    $svc = Get-Service -Name $SplitService -ErrorAction SilentlyContinue
    if (-not $svc) {
        if (-not (Test-IsAdmin)) {
            Write-Host 'Installing split tunnel requires Administrator. Re-launching...'
            Start-Process powershell.exe -Verb RunAs -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-SplitConfig', "`"$SplitConfig`"", '-FullConfig', "`"$FullConfig`""
            ) -Wait
            exit $LASTEXITCODE
        }
        if (Test-Path $FullConfig) {
            Write-Host "Removing full-tunnel service (if present)..."
            & $WireGuardExe /uninstalltunnelservice $FullConfig | Out-Null
        }
        Write-Host "Installing split tunnel: $SplitConfig"
        & $WireGuardExe /installtunnelservice $SplitConfig | Out-Null
    }
}

Ensure-SplitTunnelInstalled

$full = Get-Service -Name $FullService -ErrorAction SilentlyContinue
if ($full -and $full.Status -eq 'Running') {
    if (Test-IsAdmin) {
        Write-Host 'Stopping full-tunnel WireGuard...'
        Stop-Service -Name $FullService -Force
    } else {
        Write-Warning "Full tunnel $FullService is running; stop it manually or re-run as Administrator."
    }
}

$split = Get-Service -Name $SplitService -ErrorAction SilentlyContinue
if (-not $split) {
    throw "Split tunnel service not found after install: $SplitService"
}
if ($split.Status -ne 'Running') {
    try {
        Start-Service -Name $SplitService
    } catch {
        if (-not (Test-IsAdmin)) {
            Write-Host 'Starting tunnel requires Administrator. Re-launching...'
            Start-Process powershell.exe -Verb RunAs -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-SplitConfig', "`"$SplitConfig`"", '-FullConfig', "`"$FullConfig`""
            ) -Wait
            exit $LASTEXITCODE
        }
        throw
    }
}

Write-Host "OK: $SplitService is Running"
Write-Host "Routes SotaOCR + OpenAI API IPs through VPN; other traffic stays direct."
Get-Service -Name $SplitService | Format-Table Name, Status -AutoSize
