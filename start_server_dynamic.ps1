#Requires -Version 5.1
<#
.SYNOPSIS
    Launch OVMS in dynamic config mode (delegates to Python Core CLI).
#>

param(
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$argsList = @("-m", "tools.core.cli", "start", "ovms")

& $PYTHON_EXE @argsList
exit $LASTEXITCODE
