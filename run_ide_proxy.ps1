#Requires -Version 5.1
<#
.SYNOPSIS
    Starts the IDE Gateway Proxy (delegates to Python Core CLI).
#>

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$argsList = @("-m", "tools.core.cli", "start", "gateway")

& $PYTHON_EXE @argsList
exit $LASTEXITCODE
