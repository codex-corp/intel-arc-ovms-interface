#Requires -Version 5.1
<#
.SYNOPSIS
    Command-based local model control (status/list/switch/rollback + native OVMS lifecycle).
.EXAMPLE
    .\manage_models.ps1 status
    .\manage_models.ps1 list
    .\manage_models.ps1 switch Qwen3-4B
    .\manage_models.ps1 pull OpenVINO/Qwen3-4B-int4-ov -Name qwen3-4b
    .\manage_models.ps1 configure qwen3-4b -Path ".\models\qwen3-4b"
    .\manage_models.ps1 enable qwen3-4b
    .\manage_models.ps1 disable qwen3-4b
    .\manage_models.ps1 reload
    .\manage_models.ps1 rollback
#>

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("status", "list", "switch", "rollback", "native-list", "pull", "configure", "enable", "disable", "reload")]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Model,

    [string]$Path,
    [string]$Name,
    [string]$RepositoryPath,
    [string]$ConfigPath,
    [ValidateSet("text_generation", "embeddings", "rerank", "image_generation", "text2speech", "speech2text")]
    [string]$Task = "text_generation",
    [string]$Device = "GPU",
    [ValidateSet("Safe", "Balanced", "Fast")]
    [string]$PerformanceProfile = "Balanced",
    [string]$GgufFilename,
    [switch]$Overwrite,
    [switch]$NoReload,
    [int]$Timeout = 180,
    [switch]$NoWait,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$nativeCommands = @("native-list", "pull", "configure", "enable", "disable", "reload")
if ($nativeCommands -contains $Command) {
    $nativeCommand = if ($Command -eq "native-list") { "list" } else { $Command }
    $lifecycle = Join-Path $ScriptDir "Invoke-OvmsLifecycle.ps1"
    $nativeArgs = @($nativeCommand)

    switch ($Command) {
        "native-list" {
            if ($RepositoryPath) { $nativeArgs += @("-RepositoryPath", $RepositoryPath) }
        }
        "pull" {
            if (-not $Model) { throw "pull command requires a source model argument." }
            $nativeArgs += @("-SourceModel", $Model, "-Task", $Task, "-Device", $Device, "-PerformanceProfile", $PerformanceProfile)
            if ($Name) { $nativeArgs += @("-Name", $Name) }
            if ($RepositoryPath) { $nativeArgs += @("-RepositoryPath", $RepositoryPath) }
            if ($GgufFilename) { $nativeArgs += @("-GgufFilename", $GgufFilename) }
            if ($Overwrite) { $nativeArgs += "-Overwrite" }
        }
        "configure" {
            if (-not $Path) { throw "configure command requires -Path." }
            $nativeArgs += @("-ModelPath", $Path, "-Task", $Task, "-Device", $Device, "-PerformanceProfile", $PerformanceProfile)
            if ($Model) { $nativeArgs += @("-Model", $Model) }
            if ($Name) { $nativeArgs += @("-Name", $Name) }
        }
        "enable" {
            if (-not $Model -and -not $Name) { throw "enable command requires a model name." }
            if ($Model) { $nativeArgs += @("-Model", $Model) }
            if ($Name) { $nativeArgs += @("-Name", $Name) }
            if ($Path) { $nativeArgs += @("-ModelPath", $Path) }
            if ($ConfigPath) { $nativeArgs += @("-ConfigPath", $ConfigPath) }
            if ($NoReload) { $nativeArgs += "-NoReload" }
        }
        "disable" {
            if (-not $Model -and -not $Name) { throw "disable command requires a model name." }
            if ($Model) { $nativeArgs += @("-Model", $Model) }
            if ($Name) { $nativeArgs += @("-Name", $Name) }
            if ($ConfigPath) { $nativeArgs += @("-ConfigPath", $ConfigPath) }
            if ($NoReload) { $nativeArgs += "-NoReload" }
        }
        "reload" {
            if ($ConfigPath) { $nativeArgs += @("-ConfigPath", $ConfigPath) }
        }
    }

    & $lifecycle @nativeArgs
    exit $LASTEXITCODE
}

# Existing hot-swap flow is preserved unchanged.
& "$ScriptDir\Initialize-DynamicConfig.ps1"

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
