#Requires -Version 5.1
param([switch]$VerboseOutput)
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Settings = Get-Content (Join-Path $ScriptDir "settings.json") -Raw | ConvertFrom-Json
$OvmsDir = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.ovms_dir))
$ConfigPath = Join-Path $ScriptDir "config.json"
if (-not (Test-Path $ConfigPath)) { throw "config.json not found. Run .\\install_all.ps1 first." }
if (-not (Test-Path (Join-Path $OvmsDir "ovms.exe"))) { throw "ovms.exe not found. Run .\\setup_ovms.ps1 first." }
$LogLevel = if ($VerboseOutput) { "INFO" } else { [string]$Settings.server.log_level }
$RestPort = [int]$Settings.server.rest_port
$GrpcPort = [int]$Settings.server.grpc_port
Write-Host "Launching OVMS from config.json..." -ForegroundColor Cyan
cmd /c "cd /d `"$OvmsDir`" && setupvars.bat > NUL 2>&1 && ovms.exe --config_path `"$ConfigPath`" --port $GrpcPort --rest_port $RestPort --log_level $LogLevel"
