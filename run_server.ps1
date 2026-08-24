#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the OpenVINO Model Server for IDE/Agent integration
.DESCRIPTION
    Launches OVMS with Qwen2.5-Coder-7B on Intel Arc A750.
    Displays configuration details needed for PhpStorm, VS Code, etc.
#>

param([switch]$VerboseOutput, [switch]$Proxy, [switch]$ShowProxy)

$ErrorActionPreference = "Stop"

# -ShowProxy implies -Proxy
if ($ShowProxy) { $Proxy = $true }

# --- Load Configuration ---
. "$PSScriptRoot\Load-Config.ps1"

# Configuration Mappings (for script compatibility)
$Port = $OVMS_PORT
$ModelName = $MODEL_NAME
$BaseUrl = "http://localhost:$Port/v3"
$ReadinessScript = Join-Path $PSScriptRoot "Test-OvmsReady.ps1"

# Check whether the expected OVMS model is actually ready, not just whether the TCP port is open.
& $ReadinessScript -Port $Port -ModelName $ModelName -Quiet
$OvmsReady = ($LASTEXITCODE -eq 0)

if ($OvmsReady) {
    Write-Host ""
    Write-Host "✅ Server is already running on port $Port" -ForegroundColor Green
    Write-Host ""
    Write-Host "IDE Configuration Details:" -ForegroundColor Cyan
    Write-Host "--------------------------" -ForegroundColor Gray
    Write-Host "Base URL:   $BaseUrl" -ForegroundColor White
    Write-Host "API Key:    sk-dummy" -ForegroundColor White
    Write-Host "Model Name: $ModelName" -ForegroundColor White
    Write-Host ""

    # Still launch proxy if requested (even when OVMS is already running)
    if ($Proxy) {
        $ProxyPort = $PROXY_PORT
        $ProxyRunning = Test-NetConnection -ComputerName localhost -Port $ProxyPort -InformationLevel Quiet -ErrorAction SilentlyContinue -WarningAction SilentlyContinue
        if ($ProxyRunning) {
            Write-Host "✅ Proxy is already running on port $ProxyPort" -ForegroundColor Green
        }
        else {
            if ($ShowProxy) {
                Write-Host "🚀 Starting Proxy (new window)..." -ForegroundColor Cyan
                Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$PSScriptRoot\run_ide_proxy.ps1" -WindowStyle Normal
            }
            else {
                Write-Host "🚀 Starting Proxy (minimized)..." -ForegroundColor Cyan
                Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$PSScriptRoot\run_ide_proxy.ps1" -WindowStyle Hidden
            }
        }
    }

    Write-Host "Press any key to exit..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 0
}

# A process may own the REST port without being the configured OVMS model. Fail clearly instead of launching into a port conflict.
$PortInUse = Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -ErrorAction SilentlyContinue -WarningAction SilentlyContinue
if ($PortInUse) {
    throw "Port $Port is already in use, but the configured OVMS model '$ModelName' is not ready. Check the existing process or OVMS logs."
}

# If not running, launch it
Write-Host ""
Write-Host "🚀 Starting AI Server for IDE Integration..." -ForegroundColor Cyan
Write-Host "   Model: $ModelName (Intel Arc A750)" -ForegroundColor DarkGray

# Optional Proxy Launch
if ($Proxy) {
    if ($ShowProxy) {
        Write-Host "   Proxy: Enabled (Launching in new window)..." -ForegroundColor DarkGray
        Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$PSScriptRoot\run_ide_proxy.ps1" -WindowStyle Normal
    }
    else {
        Write-Host "   Proxy: Enabled (Minimized window)..." -ForegroundColor DarkGray
        Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "$PSScriptRoot\run_ide_proxy.ps1" -WindowStyle Hidden
    }
}

# Display Config for User Copy-Paste
Write-Host ""
Write-Host "📋 Configure your IDE (PhpStorm / VS Code) with:" -ForegroundColor Yellow
Write-Host "   Base URL:   $BaseUrl" -ForegroundColor White
Write-Host "   API Key:    sk-dummy" -ForegroundColor White
Write-Host "   Model:      $ModelName" -ForegroundColor White
Write-Host ""

# Launch start_server.ps1
& "$PSScriptRoot\start_server.ps1" -VerboseOutput:$VerboseOutput
