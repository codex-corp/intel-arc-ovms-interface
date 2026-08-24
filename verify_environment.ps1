#Requires -Version 5.1
$ErrorActionPreference = "Continue"
$ScriptDir = $PSScriptRoot
$Settings = Get-Content (Join-Path $ScriptDir "settings.json") -Raw | ConvertFrom-Json
$Manifest = Get-Content (Join-Path $ScriptDir "runtime-manifest.json") -Raw | ConvertFrom-Json
$fail = 0; $warn = 0
function Check([string]$Name, [bool]$Ok, [string]$Detail, [switch]$WarningOnly) {
  if ($Ok) { Write-Host "[PASS] $Name - $Detail" -ForegroundColor Green }
  elseif ($WarningOnly) { $script:warn++; Write-Host "[WARN] $Name - $Detail" -ForegroundColor Yellow }
  else { $script:fail++; Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red }
}
$os = Get-CimInstance Win32_OperatingSystem
Check "Windows 11" ([int]$os.BuildNumber -ge 22621) "Build $($os.BuildNumber)"
$gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "Intel.*Arc|Arc.*Graphics" } | Select-Object -First 1
Check "Intel Arc GPU" ($null -ne $gpu) $(if($gpu){$gpu.Name}else{"not detected"})
if ($gpu) {
  $parts = $gpu.DriverVersion -split '\\.'; $build = if($parts.Count -ge 4){[int]$parts[-1]}else{0}
  Check "Intel driver" ($build -ge [int]$Manifest.minimum_driver_build) $gpu.DriverVersion -WarningOnly
}
$py = Get-Command py -ErrorAction SilentlyContinue
Check "Python launcher" ($null -ne $py) "Python $($Manifest.python) required for helper tools" -WarningOnly
$OvmsDir = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.ovms_dir))
$exe = Join-Path $OvmsDir "ovms.exe"
Check "OVMS runtime" (Test-Path $exe) $(if(Test-Path $exe){$exe}else{"not installed yet"}) -WarningOnly
if (Test-Path $exe) {
  try { $version = & $exe --version 2>&1 | Out-String; Check "OVMS version" ($version -match [regex]::Escape([string]$Manifest.ovms.version)) $version.Trim() -WarningOnly } catch { Check "OVMS version" $false $_.Exception.Message -WarningOnly }
}
Write-Host "Environment: $fail failure(s), $warn warning(s)."
exit $(if($fail -gt 0){1}else{0})
