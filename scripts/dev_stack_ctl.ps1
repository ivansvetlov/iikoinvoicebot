# Fast restart PyCharm stack 1/2/5. Wrapper over scripts/dev_stack_ctl.py
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status')]
    [string]$Action = 'restart',

    [string]$Only = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptPath
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "venv python not found: $Python"
}

$Args = @($Action)
if ($Only) {
    $Args += @('--only', $Only)
}

& $Python (Join-Path $Root 'scripts\dev_stack_ctl.py') @Args
exit $LASTEXITCODE
