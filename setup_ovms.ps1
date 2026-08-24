#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Manifest = Get-Content (Join-Path $ScriptDir "runtime-manifest.json") -Raw | ConvertFrom-Json
$Settings = Get-Content (Join-Path $ScriptDir "settings.json") -Raw | ConvertFrom-Json
$OvmsDir = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.ovms_dir))
$Version = [string]$Manifest.ovms.version
$ReleaseTag = [string]$Manifest.ovms.release_tag
$AssetPattern = [string]$Manifest.ovms.windows_asset_pattern
New-Item -ItemType Directory -Path (Split-Path $OvmsDir -Parent) -Force | Out-Null
if (Test-Path (Join-Path $OvmsDir "ovms.exe")) {
    $ver = & (Join-Path $OvmsDir "ovms.exe") --version 2>&1
    if (($ver | Out-String) -match [regex]::Escape($Version)) { Write-Host "OVMS $Version already installed." -ForegroundColor Green; exit 0 }
    Write-Host "Existing OVMS differs from requested $Version; refreshing..." -ForegroundColor Yellow
}
$releaseUrl = "https://api.github.com/repos/openvinotoolkit/model_server/releases/tags/$ReleaseTag"
$release = Invoke-RestMethod -Uri $releaseUrl -Headers @{"Accept"="application/vnd.github+json"}
$asset = $release.assets | Where-Object { $_.name -match $AssetPattern } | Select-Object -First 1
if (-not $asset) { throw "No Windows OVMS asset matching '$AssetPattern' found for $ReleaseTag." }
$zipPath = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
$parent = Split-Path $OvmsDir -Parent
Expand-Archive -Path $zipPath -DestinationPath $parent -Force
Remove-Item $zipPath -Force
if (-not (Test-Path (Join-Path $OvmsDir "ovms.exe"))) { throw "OVMS extraction completed but ovms.exe was not found at $OvmsDir." }
Write-Host "OVMS $Version ready at $OvmsDir" -ForegroundColor Green
