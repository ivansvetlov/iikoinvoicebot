param(
    [switch]$InstallIfMissing,
    [switch]$LoginIfLoggedOut,
    [switch]$CopySshCommand
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-TailscaleExe {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $defaultPath = "C:\Program Files\Tailscale\tailscale.exe"
    if (Test-Path $defaultPath) {
        return $defaultPath
    }

    return $null
}

function Ensure-TailscaleInstalled {
    $tsExe = Get-TailscaleExe
    if ($tsExe) {
        return $tsExe
    }

    if (-not $InstallIfMissing) {
        throw "Tailscale is not installed (or not in PATH). Re-run with -InstallIfMissing."
    }

    Write-Host "Installing Tailscale via winget..."
    winget install --id Tailscale.Tailscale --exact --silent --accept-source-agreements --accept-package-agreements | Out-Host

    $tsExe = Get-TailscaleExe
    if (-not $tsExe) {
        throw "Tailscale install command finished, but tailscale.exe was not found."
    }

    return $tsExe
}

function Get-TailscaleState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )

    $service = Get-Service -Name Tailscale -ErrorAction SilentlyContinue

    $statusOut = & $ExePath status 2>&1
    $statusCode = $LASTEXITCODE

    $loggedOut = $false
    $loginUrl = $null
    $tailscaleIp = $null

    if ($statusCode -ne 0) {
        $statusText = ($statusOut | Out-String).Trim()
        if ($statusText -match "Logged out\.\s*Log in at:\s*(\S+)") {
            $loggedOut = $true
            $loginUrl = $Matches[1]
        } else {
            $loggedOut = $true
        }
    } else {
        $ipOut = & $ExePath ip -4 2>$null
        if ($LASTEXITCODE -eq 0) {
            $tailscaleIp = ($ipOut | Select-Object -First 1).Trim()
        }
    }

    [PSCustomObject]@{
        ServiceStatus = if ($service) { $service.Status } else { "NotInstalled" }
        ServiceStartType = if ($service) { $service.StartType } else { "Unknown" }
        LoggedOut = $loggedOut
        LoginUrl = $loginUrl
        TailscaleIPv4 = $tailscaleIp
        StatusOutput = ($statusOut | Out-String).Trim()
    }
}

$tailscaleExe = Ensure-TailscaleInstalled

Write-Host "tailscale.exe: $tailscaleExe"
Write-Host "Version:"
& $tailscaleExe version | Out-Host

$state = Get-TailscaleState -ExePath $tailscaleExe

Write-Host ""
Write-Host "Service:"
Write-Host "  Status: $($state.ServiceStatus)"
Write-Host "  StartType: $($state.ServiceStartType)"

if ($state.LoggedOut -and $LoginIfLoggedOut) {
    Write-Host ""
    Write-Host "Tailscale is logged out. Starting login flow..."
    $upOut = & $tailscaleExe up 2>&1
    $upText = ($upOut | Out-String).Trim()
    Write-Host $upText

    if ($upText -match "https://\S+") {
        $login = $Matches[0]
        Write-Host ""
        Write-Host "Open this URL on Windows OR phone (same account):"
        Write-Host "  $login"
    }

    $state = Get-TailscaleState -ExePath $tailscaleExe
}

Write-Host ""
if ($state.LoggedOut) {
    Write-Host "State: LOGGED OUT"
    if ($state.LoginUrl) {
        Write-Host "Login URL: $($state.LoginUrl)"
    } else {
        Write-Host "Run: `"$tailscaleExe`" up"
    }
    Write-Host ""
    Write-Host "After login, re-run this script to get a stable Tailscale IP for SSH."
    exit 0
}

Write-Host "State: LOGGED IN"
if (-not $state.TailscaleIPv4) {
    Write-Host "Could not resolve Tailscale IPv4."
    Write-Host "Raw status:"
    Write-Host $state.StatusOutput
    exit 0
}

$user = $env:USERNAME
$sshCmd = "ssh $user@$($state.TailscaleIPv4)"

Write-Host "Tailscale IPv4: $($state.TailscaleIPv4)"
Write-Host ""
Write-Host "Use from Termux:"
Write-Host "  $sshCmd"
Write-Host ""
Write-Host "If toolkit aliases are installed in Termux:"
Write-Host "  wsetip $($state.TailscaleIPv4)"
Write-Host "  wssh"

if ($CopySshCommand) {
    Set-Clipboard -Value $sshCmd
    Write-Host ""
    Write-Host "SSH command copied to clipboard."
}
