param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    throw "Run this script from elevated PowerShell (Run as Administrator)."
}

Write-Host "[1/4] Installing OpenSSH Server capability (if missing)..."
$cap = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
if ($cap.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
}

Write-Host "[2/4] Enabling and starting sshd service..."
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

Write-Host "[3/4] Ensuring firewall rule for TCP/22..."
$fw = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if (-not $fw) {
    New-NetFirewallRule `
        -Name "OpenSSH-Server-In-TCP" `
        -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort 22 | Out-Null
} else {
    Enable-NetFirewallRule -Name "OpenSSH-Server-In-TCP" | Out-Null
}

Write-Host "[4/4] Status:"
Get-Service sshd | Select-Object Name, Status, StartType | Format-Table -AutoSize
Write-Host "Done. Next: run 02_add_termux_pubkey.ps1"

