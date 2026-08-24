#Requires -Version 5.1
param([switch]$VerboseOutput, [switch]$Proxy, [switch]$ShowProxy)
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Settings = Get-Content (Join-Path $ScriptDir "settings.json") -Raw | ConvertFrom-Json
$RestPort = [int]$Settings.server.rest_port
$ProxyPort = [int]$Settings.proxy.port
function Test-OvmsReady {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$RestPort/v3/models" -TimeoutSec 3
        return $null -ne $r.data
    } catch { return $false }
}
if (-not (Test-OvmsReady)) {
    Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$ScriptDir\\start_server.ps1", $(if ($VerboseOutput) { "-VerboseOutput" } else { "" }) -WindowStyle Normal
    for ($i=0; $i -lt 60 -and -not (Test-OvmsReady); $i++) { Start-Sleep -Seconds 2 }
    if (-not (Test-OvmsReady)) { throw "OVMS did not become ready." }
}
Write-Host "OVMS ready: http://127.0.0.1:$RestPort/v3" -ForegroundColor Green
if ($Proxy -or $Settings.proxy.enabled) {
    if ($ShowProxy) { & "$ScriptDir\\run_ide_proxy.ps1" }
    else { Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$ScriptDir\\run_ide_proxy.ps1" -WindowStyle Hidden }
    Write-Host "Compatibility gateway: http://127.0.0.1:$ProxyPort/v3" -ForegroundColor Cyan
}
