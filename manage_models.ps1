#Requires -Version 5.1
<#
.SYNOPSIS
    Command-based local model control (status/list/switch/rollback).
.EXAMPLE
    .\manage_models.ps1 status
    .\manage_models.ps1 list
    .\manage_models.ps1 switch Qwen3-4B
    .\manage_models.ps1 switch custom-model --path "g:\ai-hub\llama\models\custom-int4-ov"
    .\manage_models.ps1 rollback
#>

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("status", "list", "switch", "rollback")]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Model,

    [string]$Path,
    [int]$Timeout = 180,
    [switch]$NoWait,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$ManagerScript = Join-Path $ScriptDir "tools\model_manager\manage_models.py"
$argsList = @($ManagerScript, "--root", $ScriptDir, $Command)

if ($Command -eq "switch") {
    if (-not $Model) {
        throw "switch command requires a model argument."
    }
    $argsList += $Model
    if ($Path) { $argsList += @("--path", $Path) }
    if ($Timeout) { $argsList += @("--timeout", "$Timeout") }
    if ($NoWait) { $argsList += "--no-wait" }
    if ($DryRun) { $argsList += "--dry-run" }
}

& $PYTHON_EXE @argsList
exit $LASTEXITCODE

