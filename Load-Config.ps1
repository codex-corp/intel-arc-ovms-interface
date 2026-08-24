#Requires -Version 5.1
# Backward-compatibility adapter. New code should read settings.json directly.
$ScriptDir = $PSScriptRoot
$SettingsPath = Join-Path $ScriptDir "settings.json"
if (-not (Test-Path $SettingsPath)) { throw "settings.json not found at $SettingsPath" }
$Settings = Get-Content $SettingsPath -Raw | ConvertFrom-Json
Set-Variable -Name "AI_INTERFACE_DIR" -Value $ScriptDir -Scope Global
Set-Variable -Name "AI_HUB_DIR" -Value ([System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.model_repository))) -Scope Global
Set-Variable -Name "VENV_DIR" -Value (Join-Path $ScriptDir ".venv") -Scope Global
Set-Variable -Name "OVMS_DIR" -Value ([System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Settings.paths.ovms_dir))) -Scope Global
Set-Variable -Name "OVMS_PORT" -Value ([int]$Settings.server.rest_port) -Scope Global
Set-Variable -Name "OVMS_GRPC_PORT" -Value ([int]$Settings.server.grpc_port) -Scope Global
Set-Variable -Name "PROXY_PORT" -Value ([int]$Settings.proxy.port) -Scope Global
Set-Variable -Name "PROXY_SCRIPT" -Value (Join-Path $ScriptDir "proxy_server.py") -Scope Global
Set-Variable -Name "PYTHON_EXE" -Value (Join-Path $ScriptDir ".venv\\Scripts\\python.exe") -Scope Global
