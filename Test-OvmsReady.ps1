#Requires -Version 5.1
<#
.SYNOPSIS
    Checks whether OVMS is reachable and serving the expected model (delegates to Python Core CLI).
#>

param(
    [int]$Port,
    [string]$ModelName,
    [int]$TimeoutSec = 5,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

if (-not $Port) { $Port = [int]$OVMS_PORT }
if (-not $ModelName) { $ModelName = $MODEL_NAME }

$argsList = @("-m", "tools.core.cli", "test-ready", "--port", "$Port", "--timeout", "$TimeoutSec")
if ($ModelName) {
    $argsList += @("--model", $ModelName)
}
if ($Quiet) {
    $argsList += "--json"
    $null = & $PYTHON_EXE @argsList
} else {
    & $PYTHON_EXE @argsList
}

exit $LASTEXITCODE
