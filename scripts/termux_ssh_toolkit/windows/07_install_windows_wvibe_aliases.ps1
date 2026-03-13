param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$UvBinPath = "$env:USERPROFILE\.local\bin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectPath)) {
    throw "Project path not found: $ProjectPath"
}

$shimPath = Join-Path $ProjectPath "scripts\termux_ssh_toolkit\windows\07_wvibe_windows_shim.ps1"
if (-not (Test-Path -LiteralPath $shimPath)) {
    throw "Shim script not found: $shimPath"
}

New-Item -ItemType Directory -Path $UvBinPath -Force | Out-Null

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$psExe = "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

$wvibeCmdPath = Join-Path $UvBinPath "wvibe.cmd"
$wvibeCmd = @"
@echo off
setlocal
"$psExe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$shimPath" -ProjectPath "$ProjectPath" -UvBinPath "$UvBinPath" %*
exit /b %ERRORLEVEL%
"@
[System.IO.File]::WriteAllText($wvibeCmdPath, $wvibeCmd, $utf8NoBom)

$wreconnectCmdPath = Join-Path $UvBinPath "wreconnect.cmd"
$wreconnectCmd = @"
@echo off
setlocal
call "%~dp0wvibe.cmd" reconnect %*
exit /b %ERRORLEVEL%
"@
[System.IO.File]::WriteAllText($wreconnectCmdPath, $wreconnectCmd, $utf8NoBom)

$wmcpCmdPath = Join-Path $UvBinPath "wmcp.cmd"
$wmcpCmd = @"
@echo off
setlocal
call "%~dp0wvibe.cmd" mcp %*
exit /b %ERRORLEVEL%
"@
[System.IO.File]::WriteAllText($wmcpCmdPath, $wmcpCmd, $utf8NoBom)

$pathEntries = @()
if ($env:Path) {
    $pathEntries = $env:Path.Split(";") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}
$inPath = $false
foreach ($entry in $pathEntries) {
    if ($entry.TrimEnd("\") -ieq $UvBinPath.TrimEnd("\")) {
        $inPath = $true
        break
    }
}

Write-Host "[ok] installed:"
Write-Host " - $wvibeCmdPath"
Write-Host " - $wreconnectCmdPath"
Write-Host " - $wmcpCmdPath"
if (-not $inPath) {
    Write-Host "[warn] $UvBinPath is not in PATH for this session."
    Write-Host "[next] reopen terminal or run:"
    Write-Host "  `$env:Path = '$UvBinPath;' + `$env:Path"
}

Write-Host "[next] test commands:"
Write-Host "  wvibe doctor"
Write-Host "  wvibe ask --no-bootstrap `"Reply exactly: OK`""
