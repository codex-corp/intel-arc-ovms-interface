#Requires -Version 5.1
<#
.SYNOPSIS
    Initializes dynamic OVMS state from the existing config.env values.
.DESCRIPTION
    Creates config.json and the existing model-manager registry only when they are missing.
    Existing state is preserved and validated; the current configured model is added to the registry if needed.
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
    try {
        $existingConfig = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if (-not $existingConfig.model_config_list -or -not $existingConfig.model_config_list[0].config) {
            throw "missing model_config_list[0].config"
        }
        Write-Host "  Dynamic config already exists and is valid: $ConfigPath" -ForegroundColor DarkGray
    }
    catch {
        throw "Existing config.json is invalid. Refusing to overwrite it automatically: $($_.Exception.Message)"
    }
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
    try {
        $registry = Get-Content $RegistryPath -Raw | ConvertFrom-Json
        if (-not $registry.models) {
            throw "missing 'models' object"
        }

        $knownModel = $registry.models.PSObject.Properties[$MODEL_NAME]
        if (-not $knownModel) {
            $registry.models | Add-Member -NotePropertyName $MODEL_NAME -NotePropertyValue $MODEL_PATH
            $registry | ConvertTo-Json -Depth 6 | Set-Content -Path $RegistryPath -Encoding UTF8
            Write-Host "  Added current model to existing registry: $MODEL_NAME" -ForegroundColor Green
        } else {
            Write-Host "  Model registry already contains current model: $RegistryPath" -ForegroundColor DarkGray
        }
    }
    catch {
        throw "Existing model registry is invalid. Refusing to overwrite it automatically: $($_.Exception.Message)"
    }
}
