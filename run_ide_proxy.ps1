#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Settings = Get-Content (Join-Path $ScriptDir "settings.json") -Raw | ConvertFrom-Json
$RestPort = [int]$Settings.server.rest_port
for ($i=0; $i -lt 60; $i++) {
    try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:$RestPort/v3/models" -TimeoutSec 3; break } catch { Start-Sleep -Seconds 2 }
}
$Python = Join-Path $ScriptDir ".venv\\Scripts\\python.exe"
if (-not (Test-Path $Python)) { throw "Python venv missing. Run .\\install_all.ps1 first." }
& $Python (Join-Path $ScriptDir "proxy_server.py")
exit $LASTEXITCODE
