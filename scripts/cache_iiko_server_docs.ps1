param(
    [string]$SourcesFile = "iiko_server_docs/SOURCES.txt",
    [string]$OutputDir = "iiko_server_docs",
    [int]$TimeoutSec = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepoPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return (Join-Path $repoRoot $PathValue)
}

function Get-SafeFileName {
    param([string]$Url)
    $u = [System.Uri]$Url
    $urlHost = $u.Host.Replace(".", "_")
    $path = $u.AbsolutePath.Trim("/")
    if ([string]::IsNullOrWhiteSpace($path)) {
        $path = "root"
    }
    $path = ($path -replace "[^A-Za-z0-9_\-\/]+", "_").Replace("/", "__")
    return "${urlHost}__${path}.html"
}

function Resolve-FetchUrl {
    param([string]$Url)

    $uri = [System.Uri]$Url
    $fragment = $uri.Fragment

    if ($fragment.StartsWith("#!")) {
        $fragPath = $fragment.Substring(2).Trim("/")
        if (-not [string]::IsNullOrWhiteSpace($fragPath)) {
            $path = $uri.AbsolutePath.TrimEnd("/")
            $resolvedPath = "$path/$fragPath"
            $builder = [System.UriBuilder]$uri
            $builder.Path = $resolvedPath
            $builder.Fragment = ""
            return $builder.Uri.AbsoluteUri
        }
    }

    if ($Url.Contains("#")) {
        return $Url.Split("#")[0]
    }

    return $Url
}

$resolvedSourcesFile = Resolve-RepoPath -PathValue $SourcesFile
$resolvedOutputDir = Resolve-RepoPath -PathValue $OutputDir

if (-not (Test-Path $resolvedSourcesFile)) {
    throw "Sources file not found: $resolvedSourcesFile"
}

New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

$urls = Get-Content -Path $resolvedSourcesFile -Encoding UTF8 |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }

$indexLines = @(
    "# iiko Server Docs Cache",
    "",
    "Updated (UTC): $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))",
    "",
    "## Sources",
    ""
)

foreach ($url in $urls) {
    $fetchUrl = Resolve-FetchUrl -Url $url

    $fileName = Get-SafeFileName -Url $fetchUrl
    $outPath = Join-Path $resolvedOutputDir $fileName

    try {
        $resp = Invoke-WebRequest -Uri $fetchUrl -UseBasicParsing -TimeoutSec $TimeoutSec
        Set-Content -Path $outPath -Value $resp.Content -Encoding UTF8
        $indexLines += "- OK: $url"
        $indexLines += "  - Fetch: $fetchUrl"
        $indexLines += "  - File: $fileName"
    } catch {
        $indexLines += "- FAIL: $url"
        $indexLines += "  - Fetch: $fetchUrl"
        $indexLines += "  - Error: $($_.Exception.Message)"
    }
}

$indexPath = Join-Path $resolvedOutputDir "INDEX.md"
Set-Content -Path $indexPath -Value ($indexLines -join [Environment]::NewLine) -Encoding UTF8
Write-Output "Done. Index: $indexPath"
