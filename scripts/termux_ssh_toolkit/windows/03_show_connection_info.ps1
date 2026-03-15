param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$user = $env:USERNAME
$uvBin = Join-Path $env:USERPROFILE ".local\bin"
$ipv4 = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown" -and
        $_.IPAddress -notlike "100.*"
    } |
    Select-Object -ExpandProperty IPAddress -Unique

function Get-PreferredLanIp {
    param(
        [string[]]$Candidates
    )

    if (-not $Candidates -or $Candidates.Count -eq 0) {
        return $null
    }

    $preferred = $Candidates | Where-Object { $_ -like "192.168.*" } | Select-Object -First 1
    if ($preferred) { return $preferred }

    $preferred = $Candidates | Where-Object { $_ -like "10.*" } | Select-Object -First 1
    if ($preferred) { return $preferred }

    $preferred = $Candidates | Where-Object { $_ -match "^172\.(1[6-9]|2[0-9]|3[0-1])\." } | Select-Object -First 1
    if ($preferred) { return $preferred }

    return $Candidates[0]
}

Write-Host "Windows user: $user"
Write-Host "Candidate LAN IPv4:"
$ipv4 | ForEach-Object { Write-Host " - $_" }

function Get-TailscaleInfo {
    $tsCmd = Get-Command tailscale -ErrorAction SilentlyContinue
    $tsExe = if ($tsCmd) { $tsCmd.Source } elseif (Test-Path "C:\Program Files\Tailscale\tailscale.exe") { "C:\Program Files\Tailscale\tailscale.exe" } else { $null }
    if (-not $tsExe) {
        return $null
    }

    $ipOut = & $tsExe ip -4 2>$null
    if ($LASTEXITCODE -ne 0) {
        return [PSCustomObject]@{
            Exe = $tsExe
            IPv4 = $null
        }
    }

    [PSCustomObject]@{
        Exe = $tsExe
        IPv4 = ($ipOut | Select-Object -First 1).Trim()
    }
}

if ($ipv4.Count -gt 0) {
    $first = Get-PreferredLanIp -Candidates $ipv4
    Write-Host ""
    Write-Host "Connect from Termux:"
    Write-Host "ssh $user@$first"
    Write-Host ""
    Write-Host "Run vibe on remote host:"
    Write-Host "ssh $user@$first `"powershell -NoLogo -Command `"`$env:Path='$uvBin;' + `$env:Path; vibe --version`"`""
}

$ts = Get-TailscaleInfo
if ($ts) {
    Write-Host ""
    Write-Host "Tailscale:"
    Write-Host "  cli: $($ts.Exe)"
    if ($ts.IPv4) {
        Write-Host "  IPv4: $($ts.IPv4)"
        Write-Host "Connect from Termux via Tailscale:"
        Write-Host "ssh $user@$($ts.IPv4)"
    } else {
        Write-Host "  Not logged in. Run:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\\scripts\\termux_ssh_toolkit\\windows\\11_tailscale_phone_link.ps1 -InstallIfMissing -LoginIfLoggedOut"
    }
}
