param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = 'Stop'

$root = Join-Path $env:LOCALAPPDATA 'GitHubDesktop'
if (!(Test-Path $root)) {
  throw "GitHubDesktop not found at: $root"
}

$app = Get-ChildItem -Path $root -Directory -Filter 'app-*' | Sort-Object Name -Descending | Select-Object -First 1
if (-not $app) {
  throw "No app-* folder found in: $root"
}

$git = Join-Path $app.FullName 'resources\app\git\cmd\git.exe'
if (!(Test-Path $git)) {
  throw "Embedded git.exe not found at: $git"
}

& $git @Args
exit $LASTEXITCODE
