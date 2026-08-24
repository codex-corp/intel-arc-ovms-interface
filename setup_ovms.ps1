#Requires -Version 5.1
<#
.SYNOPSIS
    Downloads and sets up OVMS Windows native binary
.DESCRIPTION
    Downloads the configured OVMS Windows native ZIP from GitHub releases,
    extracts it, and verifies the binary is functional.
#>

param(
    [switch]$AutoDownload
)

$ErrorActionPreference = "Stop"

# --- Load Configuration ---
. "$PSScriptRoot\Load-Config.ps1"

$OvmsDir = $OVMS_DIR
$CacheDir = "$AI_INTERFACE_DIR\cache"
$OvmsVersion = $OVMS_VERSION
$GithubReleasesUrl = "https://github.com/openvinotoolkit/model_server/releases"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  OVMS Windows Native Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Target version: $OvmsVersion" -ForegroundColor DarkGray
Write-Host ""

# Create directories
if (-not (Test-Path $OvmsDir)) {
    New-Item -ItemType Directory -Path $OvmsDir -Force | Out-Null
    Write-Host "  📁 Created: $OvmsDir" -ForegroundColor Green
}
if (-not (Test-Path $CacheDir)) {
    New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
    Write-Host "  📁 Created: $CacheDir" -ForegroundColor Green
}

# Check if ovms.exe already exists
if (Test-Path "$OvmsDir\ovms.exe") {
    Write-Host "  ✅ ovms.exe already exists at $OvmsDir" -ForegroundColor Green
    Write-Host ""

    # Try version check
    try {
        $ver = & "$OvmsDir\ovms.exe" --version 2>&1
        Write-Host "  Version: $ver" -ForegroundColor DarkGray
    } catch {
        Write-Host "  ⚠️  Could not get version — binary may still be valid" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "  ⚠️  ovms.exe not found at $OvmsDir" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  MANUAL DOWNLOAD REQUIRED:" -ForegroundColor White
    Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host "  1. Go to: $GithubReleasesUrl" -ForegroundColor Yellow
    Write-Host "  2. Find release matching: v$OvmsVersion (or compatible patch release)" -ForegroundColor Yellow
    Write-Host "  3. Expand 'Assets' and download the Windows ZIP" -ForegroundColor Yellow
    Write-Host "     Look for: ovms_windows*.zip" -ForegroundColor Yellow
    Write-Host "  4. Extract contents to: $OvmsDir" -ForegroundColor Yellow
    Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  After extracting, re-run this script to verify." -ForegroundColor White

    # Attempt automated download (may fail if release naming changes)
    Write-Host ""
    $attemptDownload = $AutoDownload
    if (-not $AutoDownload) {
        $attemptDownload = (Read-Host "  Attempt automatic download? (y/n)") -eq 'y'
    }

    if ($attemptDownload) {
        Write-Host "  Checking GitHub releases for v$OvmsVersion..." -ForegroundColor Yellow
        try {
            $releaseApi = "https://api.github.com/repos/openvinotoolkit/model_server/releases?per_page=20"
            $releases = Invoke-RestMethod -Uri $releaseApi -Headers @{"Accept"="application/vnd.github.v3+json"}
            $release = $releases | Where-Object { $_.tag_name -like "v$OvmsVersion*" } | Select-Object -First 1
            if (-not $release) {
                throw "No release matching v$OvmsVersion was found."
            }

            $winAsset = $release.assets | Where-Object { $_.name -match "windows" -and $_.name -match "\.zip$" } | Select-Object -First 1

            if ($winAsset) {
                $zipPath = Join-Path $env:TEMP $winAsset.name
                Write-Host "  Downloading: $($winAsset.name) ($([math]::Round($winAsset.size/1MB, 1)) MB)..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $winAsset.browser_download_url -OutFile $zipPath -UseBasicParsing

                # Extract to parent folder because zip contains 'ovms' folder
                $ExtractDir = Split-Path -Path $OvmsDir -Parent
                Write-Host "  Extracting to $ExtractDir..." -ForegroundColor Yellow
                Expand-Archive -Path $zipPath -DestinationPath $ExtractDir -Force
                Remove-Item $zipPath -Force
                Write-Host "  ✅ OVMS downloaded and extracted!" -ForegroundColor Green
            } else {
                Write-Host "  ❌ No Windows ZIP found in release $($release.tag_name). Download manually." -ForegroundColor Red
            }
        } catch {
            Write-Host "  ❌ Auto-download failed: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  Please download manually from: $GithubReleasesUrl" -ForegroundColor Yellow
        }
    }
}

Write-Host ""

# Final verification
if (Test-Path "$OvmsDir\ovms.exe") {
    Write-Host "  ✅ OVMS binary ready at: $OvmsDir\ovms.exe" -ForegroundColor Green
    Write-Host "  ✅ Cache directory ready at: $CacheDir" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Next: Run start_server.ps1 to launch the inference server." -ForegroundColor Cyan
} else {
    Write-Host "  ❌ ovms.exe still not found. Complete the manual download." -ForegroundColor Red
}
Write-Host ""
