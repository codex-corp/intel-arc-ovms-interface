#Requires -Version 5.1
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$ErrorActionPreference = "Stop"
$MaxRetries = 10
$RetryCount = 0

Write-Host "⏳ Waiting for OVMS ($OVMS_PORT)..." -ForegroundColor Yellow

do {
    if (Test-NetConnection -ComputerName localhost -Port $OVMS_PORT -InformationLevel Quiet -ErrorAction SilentlyContinue -WarningAction SilentlyContinue) {
        Write-Host "✅ OVMS is UP!" -ForegroundColor Green

        # Kill stale proxy if port is already in use
        $existing = Get-NetTCPConnection -LocalPort $PROXY_PORT -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "⚠️  Port $PROXY_PORT in use, stopping old proxy..." -ForegroundColor Yellow
            $existing | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 1
        }

        Write-Host "Starting IDE Proxy on port $PROXY_PORT..." -ForegroundColor Cyan
        & $PYTHON_EXE $PROXY_SCRIPT
        exit 0
    }
    $RetryCount++
    Start-Sleep -Seconds 3
    Write-Host "." -NoNewline -ForegroundColor DarkGray
} while ($RetryCount -lt $MaxRetries)

Write-Host ""
Write-Host "❌ OVMS did not start within 30 seconds. Run .\start_server.ps1 first." -ForegroundColor Red
exit 1
