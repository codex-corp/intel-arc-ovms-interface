#Requires -Version 5.1
<#
.SYNOPSIS
    Checks whether OVMS is reachable and serving the expected model.
.DESCRIPTION
    Uses the OpenAI-compatible /v3/models endpoint instead of treating an open TCP port as readiness.
    Returns exit code 0 when ready and 1 otherwise.
#>

param(
    [int]$Port,
    [string]$ModelName,
    [int]$TimeoutSec = 3,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

if (-not $Port) { $Port = [int]$OVMS_PORT }
if (-not $ModelName) { $ModelName = $MODEL_NAME }

try {
    $response = Invoke-RestMethod -Uri "http://localhost:$Port/v3/models" -Method Get -TimeoutSec $TimeoutSec
    $modelIds = @($response.data | ForEach-Object { [string]$_.id })

    if ($ModelName -and $modelIds -notcontains $ModelName) {
        if (-not $Quiet) {
            Write-Host "OVMS is reachable, but model '$ModelName' is not ready." -ForegroundColor Yellow
        }
        exit 1
    }

    if (-not $Quiet) {
        Write-Host "OVMS is ready on port $Port." -ForegroundColor Green
    }
    exit 0
}
catch {
    if (-not $Quiet) {
        Write-Host "OVMS is not ready on port $Port: $($_.Exception.Message)" -ForegroundColor DarkGray
    }
    exit 1
}
