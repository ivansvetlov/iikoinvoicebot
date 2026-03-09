param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("polling", "webhook")]
    [string]$Mode,
    [string]$EnvPath = ".env",
    [string]$WebhookUrl = "",
    [string]$WebhookSecret = ""
)

if (-not (Test-Path $EnvPath)) {
    throw "Env file not found: $EnvPath"
}

function Set-EnvValue {
    param(
        [string[]]$Lines,
        [string]$Key,
        [string]$Value
    )
    $found = $false
    $out = foreach ($line in $Lines) {
        if ($line -match "^\s*#") { $line; continue }
        if ($line -match "^\s*${Key}=") {
            $found = $true
            "${Key}=$Value"
        } else {
            $line
        }
    }
    if (-not $found) {
        $out += "${Key}=$Value"
    }
    return ,$out
}

$lines = Get-Content $EnvPath

if ($Mode -eq "polling") {
    $lines = Set-EnvValue -Lines $lines -Key "USE_WEBHOOK" -Value "false"
    $lines = Set-EnvValue -Lines $lines -Key "WEBHOOK_URL" -Value ""
    $lines = Set-EnvValue -Lines $lines -Key "WEBHOOK_SECRET" -Value ""
} else {
    if (-not $WebhookUrl) { throw "WebhookUrl is required for webhook mode." }
    if (-not $WebhookSecret) { throw "WebhookSecret is required for webhook mode." }
    $lines = Set-EnvValue -Lines $lines -Key "USE_WEBHOOK" -Value "true"
    $lines = Set-EnvValue -Lines $lines -Key "WEBHOOK_URL" -Value $WebhookUrl
    $lines = Set-EnvValue -Lines $lines -Key "WEBHOOK_SECRET" -Value $WebhookSecret
}

Set-Content -Path $EnvPath -Value $lines -Encoding utf8
Write-Host "Mode set to $Mode in $EnvPath"
