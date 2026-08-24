#Requires -Version 5.1
<#
.SYNOPSIS
    Initializes dynamic OVMS state from the existing config.env values.
.DESCRIPTION
    Creates config.json and the existing model-manager registry only when they are missing.
    It does not replace or migrate the current config.env flow.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

if (-not $MODEL_NAME) { throw "MODEL_NAME is not configured." }
if (-not $MODEL_PATH) { throw "MODEL_PATH is not configured." }

$ConfigPath = Join-Path $ScriptDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    $config = @{
        model_config_list = @(
            @{
                config = @{
                    name = $MODEL_NAME
                    base_path = $MODEL_PATH
                }
            }
        )
    }
    $config | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
    Write-Host "  Created dynamic config: $ConfigPath" -ForegroundColor Green
} else {
    Write-Host "  Dynamic config already exists: $ConfigPath" -ForegroundColor DarkGray
}

# Keep the current model-manager path for backward compatibility.
$ArtifactsDir = Join-Path $ScriptDir "artficats"
$RegistryPath = Join-Path $ArtifactsDir "models_registry.json"
if (-not (Test-Path $RegistryPath)) {
    New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null
    $registry = @{
        models = @{
            $MODEL_NAME = $MODEL_PATH
        }
    }
    $registry | ConvertTo-Json -Depth 6 | Set-Content -Path $RegistryPath -Encoding UTF8
    Write-Host "  Created model registry: $RegistryPath" -ForegroundColor Green
} else {
    Write-Host "  Model registry already exists: $RegistryPath" -ForegroundColor DarkGray
}
