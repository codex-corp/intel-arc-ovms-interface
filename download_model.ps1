#Requires -Version 5.1
param(
    [Parameter(Mandatory=$true, Position=0)][string]$Source,
    [string]$Name,
    [string]$Task = "text_generation",
    [string]$Device = "GPU",
    [int]$CacheSize = 2,
    [int]$MaxNumSeqs = 2
)
$ErrorActionPreference = "Stop"
Write-Warning "download_model.ps1 now delegates model preparation to the native OVMS pull lifecycle."
$argsList = @("pull", $Source, "-Task", $Task, "-Device", $Device, "-CacheSize", $CacheSize, "-MaxNumSeqs", $MaxNumSeqs)
if ($Name) { $argsList += @("-Name", $Name) }
& "$PSScriptRoot\\manage_models.ps1" @argsList
exit $LASTEXITCODE
