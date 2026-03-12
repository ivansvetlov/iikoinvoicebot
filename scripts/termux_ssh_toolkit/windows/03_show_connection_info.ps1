param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$user = $env:USERNAME
$uvBin = Join-Path $env:USERPROFILE ".local\bin"
$ipv4 = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown"
    } |
    Select-Object -ExpandProperty IPAddress -Unique

Write-Host "Windows user: $user"
Write-Host "Candidate LAN IPv4:"
$ipv4 | ForEach-Object { Write-Host " - $_" }

if ($ipv4.Count -gt 0) {
    $first = $ipv4[0]
    Write-Host ""
    Write-Host "Connect from Termux:"
    Write-Host "ssh $user@$first"
    Write-Host ""
    Write-Host "Run vibe on remote host:"
    Write-Host "ssh $user@$first `"powershell -NoLogo -Command `"`$env:Path='$uvBin;' + `$env:Path; vibe --version`"`""
}

