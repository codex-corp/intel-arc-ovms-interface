#Requires -Version 5.1
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$ErrorActionPreference = "Stop"
$MaxRetries = 60
$RetryCount = 0

Write-Host "⏳ Waiting for OVMS ($OVMS_PORT)..." -ForegroundColor Yellow

do {
    if (Test-NetConnection -ComputerName localhost -Port $OVMS_PORT -InformationLevel Quiet -ErrorAction SilentlyContinue -WarningAction SilentlyContinue) {
        Write-Host "✅ OVMS is UP!" -ForegroundColor Green

        # If proxy port is in use, only stop known proxy processes.
        $existing = Get-NetTCPConnection -LocalPort $PROXY_PORT -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "⚠️  Port $PROXY_PORT in use, checking owner process(es)..." -ForegroundColor Yellow
            $proxyLeaf = Split-Path -Leaf $PROXY_SCRIPT
            $unsafeOwnerFound = $false

            $existing | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
                $pid = $_
                $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid" -ErrorAction SilentlyContinue
                $cmdline = if ($proc) { [string]$proc.CommandLine } else { "" }

                if ($cmdline -and $cmdline.ToLower().Contains($proxyLeaf.ToLower())) {
                    Write-Host "   Stopping stale proxy process PID $pid..." -ForegroundColor DarkGray
                    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                }
                else {
                    Write-Host "❌ Port $PROXY_PORT is owned by PID $pid (not recognized as IDE proxy)." -ForegroundColor Red
                    Write-Host "   Refusing to kill unrelated process. Free the port or change PROXY_PORT in config.env." -ForegroundColor Yellow
                    $unsafeOwnerFound = $true
                }
            }

            if ($unsafeOwnerFound) {
                exit 1
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
Write-Host "❌ OVMS did not start within 180 seconds. Run .\start_server.ps1 first." -ForegroundColor Red
exit 1
