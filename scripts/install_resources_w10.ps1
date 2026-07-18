param(
    [string]$LlamaCppZipUrl = $env:LLAMACPP_ZIP_URL,
    [string]$RepoLensZipUrl = $env:REPOLENS_ZIP_URL,
    [string]$RepoLensExeUrl = $env:REPOLENS_EXE_URL,
    [string]$ModelUrl = $env:MODEL_URL
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $RepoRoot ".venv"
$DownloadsDir = Join-Path $RepoRoot "downloads"
$LlamaDir = Join-Path $RepoRoot "src\assets\LlamaCPP"
$ModelsDir = Join-Path $RepoRoot "src\assets\llmmodels"
$RepoLensDir = Join-Path $RepoRoot "src\services\repoLens"

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Download-File($Url, $Destination) {
    if ([string]::IsNullOrWhiteSpace($Url)) {
        return $false
    }
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination
    return $true
}

function Python-Command {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @("py", "-3")
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @("python")
    }
    throw "Python 3 was not found. Install Python 3.10+ from https://www.python.org/downloads/windows/ and enable 'Add python.exe to PATH'."
}

Ensure-Directory $DownloadsDir
Ensure-Directory $LlamaDir
Ensure-Directory $ModelsDir
Ensure-Directory $RepoLensDir

$python = Python-Command
if (-not (Test-Path $VenvDir)) {
    $pythonExe = $python[0]
    $pythonArgs = @()
    if ($python.Count -gt 1) {
        $pythonArgs = $python[1..($python.Count - 1)]
    }
    & $pythonExe @pythonArgs -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$llamaZip = Join-Path $DownloadsDir "llamacpp.zip"
if (Download-File $LlamaCppZipUrl $llamaZip) {
    Expand-Archive -Path $llamaZip -DestinationPath $LlamaDir -Force
}

$repolensZip = Join-Path $DownloadsDir "repolens.zip"
if (Download-File $RepoLensZipUrl $repolensZip) {
    Expand-Archive -Path $repolensZip -DestinationPath $RepoLensDir -Force
}

$repolensExe = Join-Path $RepoLensDir "repolens.exe"
Download-File $RepoLensExeUrl $repolensExe | Out-Null

if (-not [string]::IsNullOrWhiteSpace($ModelUrl)) {
    $modelName = Split-Path ([uri]$ModelUrl).AbsolutePath -Leaf
    if ([string]::IsNullOrWhiteSpace($modelName)) {
        $modelName = "model.gguf"
    }
    Download-File $ModelUrl (Join-Path $ModelsDir $modelName) | Out-Null
}

Write-Host ""
Write-Host "CodeSnippets resources are ready."
Write-Host "Run with: $VenvPython $RepoRoot\app.py"
Write-Host ""
Write-Host "Optional downloads can be supplied with:"
Write-Host "  -LlamaCppZipUrl <zip-url>"
Write-Host "  -RepoLensZipUrl <zip-url> or -RepoLensExeUrl <exe-url>"
Write-Host "  -ModelUrl <gguf-url>"
