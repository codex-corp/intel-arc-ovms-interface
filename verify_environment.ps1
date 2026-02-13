#Requires -Version 5.1
<#
.SYNOPSIS
    Intel Arc A750 + OpenVINO Environment Verification Script
.DESCRIPTION
    Verifies all prerequisites for running OVMS with GPU acceleration.
#>

$ErrorActionPreference = "Continue"

# --- Load Configuration ---
. "$PSScriptRoot\Load-Config.ps1"

$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0

function Write-Check {
  param([string]$Name, [string]$Status, [string]$Detail)
  switch ($Status) {
    "PASS" {
      Write-Host "  [PASS] $Name" -ForegroundColor Green
      if ($Detail) { Write-Host "         $Detail" -ForegroundColor DarkGray }
      $script:PassCount++
    }
    "FAIL" {
      Write-Host "  [FAIL] $Name" -ForegroundColor Red
      if ($Detail) { Write-Host "         $Detail" -ForegroundColor Yellow }
      $script:FailCount++
    }
    "WARN" {
      Write-Host "  [WARN] $Name" -ForegroundColor Yellow
      if ($Detail) { Write-Host "         $Detail" -ForegroundColor DarkGray }
      $script:WarnCount++
    }
  }
}

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  Intel Arc A750 + OpenVINO Environment Verification" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Windows Version ---
Write-Host ">> Operating System" -ForegroundColor White
$os = Get-CimInstance Win32_OperatingSystem
$build = [int]$os.BuildNumber
if ($build -ge 22621) {
  Write-Check "Windows 11 22H2+" "PASS" "$($os.Caption) (Build $build)"
}
elseif ($build -ge 22000) {
  Write-Check "Windows 11 (older build)" "WARN" "Build $build - recommend 22H2+ (22621+)"
}
else {
  Write-Check "Windows 11 required" "FAIL" "Detected: $($os.Caption) (Build $build)"
}
Write-Host ""

# --- 2. Intel Arc GPU Detection ---
Write-Host ">> Intel Arc GPU" -ForegroundColor White
$gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "Arc" }
if ($gpus) {
  foreach ($gpu in $gpus) {
    $driverVer = $gpu.DriverVersion
    Write-Check "GPU Detected" "PASS" "$($gpu.Name)"
    Write-Check "Driver Version" "PASS" "$driverVer"

    # Parse driver version
    $parts = $driverVer -split '\.'
    if ($parts.Count -ge 4) {
      $driverBuild = [int]$parts[-1]
      if ($driverBuild -ge 6078) {
        Write-Check "Driver >= 32.0.101.6078" "PASS" "Build $driverBuild"
      }
      else {
        Write-Check "Driver >= 32.0.101.6078" "FAIL" "Build $driverBuild - update from intel.com"
      }
    }

    # Dedicated VRAM
    $vramMB = [math]::Round($gpu.AdapterRAM / 1MB, 0)
    if ($vramMB -gt 0) {
      Write-Check "Dedicated VRAM" "PASS" "$vramMB MB reported by WMI"
    }
    else {
      Write-Check "Dedicated VRAM" "WARN" "WMI reports 0 MB - check Task Manager for actual value"
    }
  }
}
else {
  Write-Check "Intel Arc GPU" "FAIL" "No Intel Arc GPU detected in system"
}
Write-Host ""

# --- 3. Resizable BAR ---
Write-Host ">> Resizable BAR (ReBAR)" -ForegroundColor White
$rebarPaths = @(
  "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
  "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0001",
  "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0002"
)
$rebarFound = $false
foreach ($path in $rebarPaths) {
  $rebar = Get-ItemProperty -Path $path -Name "KMD_RebarFeatureSupport" -ErrorAction SilentlyContinue
  if ($rebar -and $rebar.KMD_RebarFeatureSupport -eq 1) {
    Write-Check "ReBAR Enabled" "PASS" "Registry key found at $path"
    $rebarFound = $true
    break
  }
}
if (-not $rebarFound) {
  Write-Check "ReBAR Status" "WARN" "Could not confirm via registry. Check BIOS: Above 4G Decoding + Re-Size BAR Support."
}
Write-Host ""

# --- 4. VC++ Redistributable ---
Write-Host ">> Visual C++ Redistributable" -ForegroundColor White
$vcredist = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" -ErrorAction SilentlyContinue
if ($vcredist) {
  Write-Check "VC++ 2015-2022 (x64)" "PASS" "Version $($vcredist.Version)"
}
else {
  Write-Check "VC++ 2015-2022 (x64)" "WARN" "Not found via registry. Download: https://aka.ms/vs/17/release/vc_redist.x64.exe"
}
Write-Host ""

# --- 5. Python ---
Write-Host ">> Python" -ForegroundColor White
$pyResult = $null
try {
  $pyResult = & python --version 2>&1
}
catch {
  # ignore
}

if ($pyResult -and ($pyResult -match "Python (\d+\.\d+)")) {
  $pyMajorMinor = $Matches[1]
  $pyVer = [version]$pyMajorMinor
  if ($pyVer -ge [version]"3.10" -and $pyVer -le [version]"3.12") {
    Write-Check "Python $pyMajorMinor" "PASS" "Supported for OpenVINO 2025.x"
  }
  else {
    Write-Check "Python $pyMajorMinor" "WARN" "OpenVINO recommends 3.10-3.12"
  }
}
else {
  Write-Check "Python" "FAIL" "Python not found in PATH"
}
Write-Host ""

# --- 6. OpenVINO Model Server (OVMS) ---
Write-Host ">> OpenVINO Model Server" -ForegroundColor White

# 6a. Check for Binary
$ovmsPath = "$OVMS_DIR\ovms.exe"
if (Test-Path $ovmsPath) {
  Write-Check "OVMS Binary" "PASS" "Found at $ovmsPath"
} else {
  Write-Check "OVMS Binary" "WARN" "Not found at default location. Ignore if using Docker/other path."
}

# 6b. Check Server Status (Port $OVMS_PORT)
$portOpen = $false
try {
  $tcp = Test-NetConnection -ComputerName localhost -Port $OVMS_PORT -InformationLevel Quiet -ErrorAction SilentlyContinue
  if ($tcp) {
    Write-Check "Server Running" "PASS" "Port $OVMS_PORT is active (REST API)"
    $portOpen = $true
  } else {
    Write-Check "Server Status" "WARN" "Port $OVMS_PORT not active. Run start_server.ps1 to launch."
  }
} catch {
  Write-Check "Server Status" "WARN" "Could not verify port $OVMS_PORT."
}

# 6c. Check Python Bindings (Optional)
Write-Host ">> OpenVINO Python (Optional)" -ForegroundColor White
$ovVersion = $null
try {
  $ovVersion = & python -c "import openvino; print(openvino.__version__)" 2>&1
} catch {}

$ovStr = ($ovVersion | Out-String).Trim()
if ($ovStr -and ($ovStr -notmatch "Error|Traceback|ModuleNotFound|No module")) {
  Write-Check "Python Package" "PASS" "Version: $ovStr"

  # Check GPU via Python if installed (good verification of driver visibility)
  try {
     $gpuName = & python -c "import openvino as ov; core = ov.Core(); print(core.get_property('GPU', 'FULL_DEVICE_NAME'))" 2>&1
     $gpuStr = ($gpuName | Out-String).Trim()
     if ($gpuStr -and $gpuStr -match "Arc") {
        Write-Check "GPU Access (Python)" "PASS" "$gpuStr"
     }
  } catch {}
} else {
  Write-Check "Python Package" "WARN" "Not installed (Optional for Binary Server)"
}
Write-Host ""

# --- Summary ---
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  Results: $script:PassCount passed, $script:WarnCount warnings, $script:FailCount failed" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

if ($script:FailCount -gt 0) {
  Write-Host "  >> Fix the failures above before proceeding." -ForegroundColor Red
}
elseif ($script:WarnCount -gt 0) {
  Write-Host "  >> Warnings detected - review before proceeding." -ForegroundColor Yellow
}
else {
  Write-Host "  >> All checks passed! Ready for OVMS setup." -ForegroundColor Green
}
Write-Host ""
