#Requires -Version 5.1
<#
.SYNOPSIS
    Launch OVMS in dynamic config mode (hot-swap friendly).
.DESCRIPTION
    Starts OpenVINO Model Server using config.json instead of fixed --model_name/--model_path.
    This mode is intended for use with .\manage_models.ps1 so model changes can be applied
    by updating config.json on disk.
#>

param(
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$LogLevel = "ERROR"
if ($VerboseOutput) { $LogLevel = "INFO" }

$ConfigPath = Join-Path $ScriptDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    throw "config.json not found at: $ConfigPath"
}

Write-Host "🚀 Launching OVMS (Dynamic Config Mode)..." -ForegroundColor Cyan
Write-Host "   Config:    $ConfigPath" -ForegroundColor DarkGray
Write-Host "   REST Port: $OVMS_PORT" -ForegroundColor DarkGray
Write-Host "   gRPC Port: $OVMS_GRPC_PORT" -ForegroundColor DarkGray
Write-Host "   Log Level: $LogLevel" -ForegroundColor DarkGray

cmd /c "cd /d "$OVMS_DIR" && setupvars.bat > NUL 2>&1 && ovms.exe --config_path "$ConfigPath" --port $OVMS_GRPC_PORT --rest_port $OVMS_PORT --log_level $LogLevel"

