param(
    [Parameter(Mandatory = $true)]
    [string]$PublicKeyPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PublicKeyPath)) {
    throw "Public key file not found: $PublicKeyPath"
}

$pubKey = (Get-Content -LiteralPath $PublicKeyPath -Raw -Encoding UTF8).Trim()
if (-not $pubKey.StartsWith("ssh-")) {
    throw "The file does not look like a valid SSH public key."
}

$sshDir = Join-Path $env:USERPROFILE ".ssh"
$authFile = Join-Path $sshDir "authorized_keys"

if (-not (Test-Path -LiteralPath $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $authFile)) {
    New-Item -ItemType File -Path $authFile -Force | Out-Null
}

$existing = @()
if (Test-Path -LiteralPath $authFile) {
    $existing = Get-Content -LiteralPath $authFile -ErrorAction SilentlyContinue | ForEach-Object { $_.Trim() }
}

if ($existing -contains $pubKey) {
    Write-Host "Public key already exists in authorized_keys."
} else {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText($authFile, "$pubKey`n", $utf8NoBom)
    Write-Host "Public key added to authorized_keys."
}

Write-Host "Done (ACLs were not modified by this script)."
Write-Host "Done. Next: run 03_show_connection_info.ps1"

