param(
    [string]$LlamaCppZipUrl = $env:LLAMACPP_ZIP_URL,
    [string]$RepoLensZipUrl = $env:REPOLENS_ZIP_URL,
    [string]$RepoLensExeUrl = $env:REPOLENS_EXE_URL,
    [string]$ModelUrl = $env:MODEL_URL
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$Bootstrap = Join-Path $ScriptDir "install_resources_w10.ps1"

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Python was not found. Installing Python 3 with winget..."
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    }
}

& $Bootstrap `
    -LlamaCppZipUrl $LlamaCppZipUrl `
    -RepoLensZipUrl $RepoLensZipUrl `
    -RepoLensExeUrl $RepoLensExeUrl `
    -ModelUrl $ModelUrl

Write-Host ""
Write-Host "Windows 11 setup complete for $RepoRoot"
