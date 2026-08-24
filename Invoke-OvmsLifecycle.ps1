#Requires -Version 5.1
<#
.SYNOPSIS
    Native OVMS lifecycle wrapper used by manage_models.ps1.
.DESCRIPTION
    Exposes OVMS-native model repository and config management without replacing
    the existing download_model.ps1 or Python hot-swap flow.
#>

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("list", "pull", "configure", "enable", "disable", "reload")]
    [string]$Command,

    [string]$Model,
    [string]$SourceModel,
    [string]$ModelPath,
    [string]$RepositoryPath,
    [string]$Name,
    [string]$ConfigPath,

    [ValidateSet("text_generation", "embeddings", "rerank", "image_generation", "text2speech", "speech2text")]
    [string]$Task = "text_generation",

    [string]$Device = "GPU",

    [ValidateSet("Safe", "Balanced", "Fast")]
    [string]$PerformanceProfile = "Balanced",

    [string]$GgufFilename,
    [switch]$Overwrite,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

function Resolve-LocalPath {
    param([string]$Value)
    if (-not $Value) { return $null }
    if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }
    return [System.IO.Path]::GetFullPath((Join-Path $ScriptDir $Value))
}

$OvmsRoot = Resolve-LocalPath $OVMS_DIR
$OvmsExe = Join-Path $OvmsRoot "ovms.exe"
$SetupVars = Join-Path $OvmsRoot "setupvars.bat"

if (-not (Test-Path $OvmsExe)) {
    throw "OVMS binary not found: $OvmsExe. Run .\setup_ovms.ps1 first."
}
if (-not (Test-Path $SetupVars)) {
    throw "OVMS setupvars.bat not found: $SetupVars"
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ScriptDir "config.json"
} else {
    $ConfigPath = Resolve-LocalPath $ConfigPath
}

if (-not $RepositoryPath) {
    if ($MODEL_PATH) {
        $resolvedCurrentModel = Resolve-LocalPath $MODEL_PATH
        $RepositoryPath = Split-Path -Parent $resolvedCurrentModel
    } else {
        $RepositoryPath = Join-Path $ScriptDir "models"
    }
} else {
    $RepositoryPath = Resolve-LocalPath $RepositoryPath
}

function Quote-CmdArg {
    param([string]$Value)
    if ($null -eq $Value) { return '""' }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-OvmsCli {
    param([string[]]$Arguments)

    $argString = ($Arguments | ForEach-Object { Quote-CmdArg $_ }) -join " "
    $commandLine = "call `"$SetupVars`" >NUL 2>&1 && `"$OvmsExe`" $argString"
    & cmd.exe /d /s /c $commandLine
    if ($LASTEXITCODE -ne 0) {
        throw "OVMS command failed with exit code $LASTEXITCODE."
    }
}

function Test-OvmsOption {
    param([string]$Option)
    $commandLine = "call `"$SetupVars`" >NUL 2>&1 && `"$OvmsExe`" --help"
    $help = (& cmd.exe /d /s /c $commandLine 2>&1 | Out-String)
    return $help -match [regex]::Escape($Option)
}

function Get-ProfileValues {
    switch ($PerformanceProfile) {
        "Safe" { return @{ CacheSize = 2; MaxSeqs = 2 } }
        "Fast" { return @{ CacheSize = 8; MaxSeqs = 8 } }
        default { return @{ CacheSize = 4; MaxSeqs = 4 } }
    }
}

function Update-LocalRegistry {
    param([string]$ModelName, [string]$PathValue)
    if (-not $ModelName -or -not $PathValue) { return }

    $ArtifactsDir = Join-Path $ScriptDir "artficats"
    $RegistryPath = Join-Path $ArtifactsDir "models_registry.json"
    New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null

    if (Test-Path $RegistryPath) {
        $registry = Get-Content $RegistryPath -Raw | ConvertFrom-Json
        if (-not $registry.models) {
            throw "Invalid model registry: missing models object at $RegistryPath"
        }
    } else {
        $registry = [pscustomobject]@{ models = [pscustomobject]@{} }
    }

    $existing = $registry.models.PSObject.Properties[$ModelName]
    if ($existing) {
        $existing.Value = $PathValue
    } else {
        $registry.models | Add-Member -NotePropertyName $ModelName -NotePropertyValue $PathValue
    }

    $temp = "$RegistryPath.tmp"
    $registry | ConvertTo-Json -Depth 8 | Set-Content -Path $temp -Encoding UTF8
    Move-Item -Path $temp -Destination $RegistryPath -Force
}

function Reload-OvmsConfig {
    if ($NoReload) { return }

    $ready = & "$ScriptDir\Test-OvmsReady.ps1" -Port ([int]$OVMS_PORT) -Quiet
    if (-not $ready) {
        Write-Host "  OVMS is not currently ready; config change will apply on next dynamic start." -ForegroundColor DarkGray
        return
    }

    $uri = "http://localhost:$OVMS_PORT/v1/config/reload"
    Write-Host "  Reloading OVMS config..." -ForegroundColor Yellow
    $response = Invoke-WebRequest -Method Post -Uri $uri -UseBasicParsing -TimeoutSec 60
    if ($response.StatusCode -notin @(200, 201)) {
        throw "OVMS config reload failed with HTTP $($response.StatusCode)."
    }
    Write-Host "  OVMS config reload accepted (HTTP $($response.StatusCode))." -ForegroundColor Green
}

switch ($Command) {
    "list" {
        Invoke-OvmsCli @("--list_models", "--model_repository_path", $RepositoryPath)
    }

    "pull" {
        $source = if ($SourceModel) { $SourceModel } else { $Model }
        if (-not $source) { throw "pull requires a Hugging Face source model." }

        $servableName = if ($Name) { $Name } else { ($source -split '/')[-1] }
        New-Item -ItemType Directory -Path $RepositoryPath -Force | Out-Null

        $args = @(
            "--pull",
            "--source_model", $source,
            "--model_repository_path", $RepositoryPath,
            "--model_name", $servableName,
            "--target_device", $Device,
            "--task", $Task
        )

        if ($Task -eq "text_generation") {
            $profile = Get-ProfileValues
            $args += @("--cache_size", "$($profile.CacheSize)", "--max_num_seqs", "$($profile.MaxSeqs)")
        }
        if ($GgufFilename) { $args += @("--gguf_filename", $GgufFilename) }
        if ($Overwrite) { $args += "--overwrite_models" }

        Invoke-OvmsCli $args

        $localPath = Join-Path $RepositoryPath $servableName
        if (Test-Path $localPath) {
            Update-LocalRegistry -ModelName $servableName -PathValue $localPath
        }
        Write-Host "  Native pull complete: $servableName" -ForegroundColor Green
    }

    "configure" {
        if (-not (Test-OvmsOption "--configure")) {
            throw "Installed OVMS does not support --configure. Upgrade OVMS to a 2026.x build."
        }
        if (-not $ModelPath) { throw "configure requires -ModelPath." }

        $resolvedModelPath = Resolve-LocalPath $ModelPath
        if (-not (Test-Path $resolvedModelPath)) {
            throw "Model path does not exist: $resolvedModelPath"
        }

        $servableName = if ($Name) { $Name } elseif ($Model) { $Model } else { Split-Path -Leaf $resolvedModelPath }
        $args = @(
            "--configure",
            "--model_path", $resolvedModelPath,
            "--model_name", $servableName,
            "--task", $Task,
            "--target_device", $Device
        )
        if ($Task -eq "text_generation") {
            $profile = Get-ProfileValues
            $args += @("--cache_size", "$($profile.CacheSize)", "--max_num_seqs", "$($profile.MaxSeqs)")
        }

        Invoke-OvmsCli $args
        Update-LocalRegistry -ModelName $servableName -PathValue $resolvedModelPath
        Write-Host "  Native configure complete: $servableName" -ForegroundColor Green
    }

    "enable" {
        $servableName = if ($Name) { $Name } else { $Model }
        if (-not $servableName) { throw "enable requires a model name." }

        & "$ScriptDir\Initialize-DynamicConfig.ps1" | Out-Null

        $resolvedModelPath = if ($ModelPath) { Resolve-LocalPath $ModelPath } else { $null }
        if (-not $resolvedModelPath) {
            $RegistryPath = Join-Path $ScriptDir "artficats\models_registry.json"
            if (Test-Path $RegistryPath) {
                $registry = Get-Content $RegistryPath -Raw | ConvertFrom-Json
                $entry = $registry.models.PSObject.Properties[$servableName]
                if ($entry) { $resolvedModelPath = [string]$entry.Value }
            }
        }
        if (-not $resolvedModelPath) { throw "enable requires -ModelPath or a registry entry for '$servableName'." }
        $resolvedModelPath = Resolve-LocalPath $resolvedModelPath
        if (-not (Test-Path $resolvedModelPath)) { throw "Model path does not exist: $resolvedModelPath" }

        Invoke-OvmsCli @(
            "--add_to_config",
            "--config_path", $ConfigPath,
            "--model_name", $servableName,
            "--model_path", $resolvedModelPath
        )
        Update-LocalRegistry -ModelName $servableName -PathValue $resolvedModelPath
        Reload-OvmsConfig
        Write-Host "  Enabled model in config: $servableName" -ForegroundColor Green
    }

    "disable" {
        $servableName = if ($Name) { $Name } else { $Model }
        if (-not $servableName) { throw "disable requires a model name." }

        & "$ScriptDir\Initialize-DynamicConfig.ps1" | Out-Null
        Invoke-OvmsCli @(
            "--remove_from_config",
            "--config_path", $ConfigPath,
            "--model_name", $servableName
        )
        Reload-OvmsConfig
        Write-Host "  Disabled model in config: $servableName" -ForegroundColor Green
    }

    "reload" {
        & "$ScriptDir\Initialize-DynamicConfig.ps1" | Out-Null
        Reload-OvmsConfig
    }
}
