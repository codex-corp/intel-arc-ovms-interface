#Requires -Version 5.1
<#
.SYNOPSIS
    Command-based local model control (delegates to Python Core CLI).
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
    [int]$Timeout = 120,
    [switch]$NoWait,
    [switch]$DryRun,
    [switch]$JsonOutput
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$argsList = @("-m", "tools.core.cli")

$targetModel = if ($Model) { $Model } else { $Name }

switch ($Command) {
    "status" {
        $argsList += "status"
    }
    "list" {
        $argsList += "list"
        if ($RepositoryPath) { $argsList += @("--repository-path", $RepositoryPath) }
    }
    "native-list" {
        $argsList += "native-list"
        if ($RepositoryPath) { $argsList += @("--repository-path", $RepositoryPath) }
    }
    "switch" {
        if (-not $targetModel) { throw "switch command requires a model argument." }
        $argsList += @("switch", $targetModel)
        if ($Path) { $argsList += @("--path", $Path) }
        if ($Timeout) { $argsList += @("--timeout", "$Timeout") }
        if ($NoWait) { $argsList += "--no-wait" }
        if ($DryRun) { $argsList += "--dry-run" }
    }
    "pull" {
        if (-not $targetModel) { throw "pull command requires a source model argument." }
        $argsList += @("pull", $targetModel)
        if ($Path) { $argsList += @("--dest", $Path) }
        if ($RepositoryPath) { $argsList += @("--repository-path", $RepositoryPath) }
        if ($Task) { $argsList += @("--task", $Task) }
        if ($Device) { $argsList += @("--device", $Device) }
        if ($PerformanceProfile) { $argsList += @("--performance-profile", $PerformanceProfile) }
        if ($GgufFilename) { $argsList += @("--gguf-filename", $GgufFilename) }
        if ($Overwrite) { $argsList += "--overwrite" }
    }
    "configure" {
        if (-not $targetModel) { throw "configure command requires a model argument." }
        $argsList += @("configure", $targetModel)
        if ($Path) { $argsList += @("--path", $Path) }
        if ($RepositoryPath) { $argsList += @("--repository-path", $RepositoryPath) }
        if ($ConfigPath) { $argsList += @("--config-path", $ConfigPath) }
        if ($Task) { $argsList += @("--task", $Task) }
        if ($Device) { $argsList += @("--device", $Device) }
        if ($PerformanceProfile) { $argsList += @("--performance-profile", $PerformanceProfile) }
        if ($NoReload) { $argsList += "--no-reload" }
        if ($DryRun) { $argsList += "--dry-run" }
    }
    "enable" {
        if (-not $targetModel) { throw "enable command requires a model argument." }
        $argsList += @("enable", $targetModel)
        if ($Path) { $argsList += @("--path", $Path) }
        if ($ConfigPath) { $argsList += @("--config-path", $ConfigPath) }
        if ($NoReload) { $argsList += "--no-reload" }
        if ($DryRun) { $argsList += "--dry-run" }
    }
    "disable" {
        if (-not $targetModel) { throw "disable command requires a model argument." }
        $argsList += @("disable", $targetModel)
        if ($ConfigPath) { $argsList += @("--config-path", $ConfigPath) }
        if ($NoReload) { $argsList += "--no-reload" }
        if ($DryRun) { $argsList += "--dry-run" }
    }
    "reload" {
        $argsList += "reload"
        if ($ConfigPath) { $argsList += @("--config-path", $ConfigPath) }
    }
    "rollback" {
        $argsList += "rollback"
        if ($ConfigPath) { $argsList += @("--config-path", $ConfigPath) }
    }
}

if ($JsonOutput) {
    $argsList += "--json"
}

& $PYTHON_EXE @argsList
exit $LASTEXITCODE
