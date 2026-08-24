#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$SettingsPath = Join-Path $ScriptDir "settings.json"
$ManifestPath = Join-Path $ScriptDir "runtime-manifest.json"
if (-not (Test-Path $SettingsPath) -or -not (Test-Path $ManifestPath)) { throw "settings.json/runtime-manifest.json missing." }
$Settings = Get-Content $SettingsPath -Raw | ConvertFrom-Json
$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$ModelRepo = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.model_repository))
New-Item -ItemType Directory -Path $ModelRepo -Force | Out-Null

Write-Host "[1/4] Environment" -ForegroundColor Cyan
& "$ScriptDir\\verify_environment.ps1"
if ($LASTEXITCODE -gt 0) { Write-Warning "Environment verification reported failures; continuing so setup can repair software dependencies." }

Write-Host "[2/4] Python environment" -ForegroundColor Cyan
$Venv = Join-Path $ScriptDir ".venv"
if (-not (Test-Path "$Venv\\Scripts\\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.11 -m venv $Venv }
    else { throw "Python 3.11 launcher not found. Install Python $($Manifest.python) and rerun." }
}
& "$Venv\\Scripts\\python.exe" -m pip install --upgrade pip | Out-Null
& "$Venv\\Scripts\\python.exe" -m pip install -r (Join-Path $ScriptDir "requirements.txt") | Out-Null

Write-Host "[3/4] OVMS runtime" -ForegroundColor Cyan
& "$ScriptDir\\setup_ovms.ps1"

Write-Host "[4/4] Runtime configuration" -ForegroundColor Cyan
$ConfigPath = Join-Path $ScriptDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    @{ model_config_list = @() } | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
}
Write-Host "Installation ready. Pull/configure a model, then run .\\start_server.ps1." -ForegroundColor Green
