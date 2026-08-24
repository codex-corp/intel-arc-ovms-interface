#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

Write-Host "PowerShell syntax checks..."
$parseErrors = @()
Get-ChildItem -Path $Root -Filter *.ps1 -File | ForEach-Object {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors) {
        $parseErrors += $errors | ForEach-Object { "$($_.Extent.File):$($_.Extent.StartLineNumber): $($_.Message)" }
    }
}

if ($parseErrors.Count -gt 0) {
    $parseErrors | ForEach-Object { Write-Error $_ }
    throw "PowerShell syntax validation failed."
}

Write-Host "Configuration contract checks..."
$examplePath = Join-Path $Root "config.env.example"
if (-not (Test-Path $examplePath)) {
    throw "config.env.example is missing."
}

$example = Get-Content $examplePath -Raw
$requiredKeys = @(
    "OVMS_VERSION=",
    "MODEL_NAME=",
    "MODEL_PATH=",
    "OVMS_PORT=",
    "OVMS_GRPC_PORT=",
    "PROXY_HOST=",
    "PROXY_PORT=",
    "PROXY_LOG_PROMPTS=",
    "PROXY_STRIP_REASONING=",
    "PROXY_INJECT_STREAM_ID="
)
foreach ($key in $requiredKeys) {
    if (-not $example.Contains($key)) {
        throw "config.env.example is missing required key: $key"
    }
}

Write-Host "Dynamic config bootstrap smoke test..."
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ovms-quality-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    Copy-Item (Join-Path $Root "Load-Config.ps1") $tempRoot
    Copy-Item (Join-Path $Root "Initialize-DynamicConfig.ps1") $tempRoot

    $modelPath = Join-Path $tempRoot "models\smoke-model"
    New-Item -ItemType Directory -Path $modelPath -Force | Out-Null

    @"
DEFAULT_MODEL_NAME=smoke-model
MODEL_NAME=smoke-model
MODEL_PATH=$modelPath
OVMS_VERSION=2026.3
OVMS_PORT=8000
"@ | Set-Content -Path (Join-Path $tempRoot "config.env") -Encoding UTF8

    & (Join-Path $tempRoot "Initialize-DynamicConfig.ps1") | Out-Null

    $configPath = Join-Path $tempRoot "config.json"
    $registryPath = Join-Path $tempRoot "artficats\models_registry.json"
    if (-not (Test-Path $configPath)) { throw "Bootstrap did not create config.json." }
    if (-not (Test-Path $registryPath)) { throw "Bootstrap did not create models_registry.json." }

    $configBefore = Get-Content $configPath -Raw
    $registryBefore = Get-Content $registryPath -Raw

    & (Join-Path $tempRoot "Initialize-DynamicConfig.ps1") | Out-Null

    if ((Get-Content $configPath -Raw) -ne $configBefore) {
        throw "Bootstrap changed existing config.json on second run."
    }
    if ((Get-Content $registryPath -Raw) -ne $registryBefore) {
        throw "Bootstrap changed existing registry on second run."
    }

    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if ($config.model_config_list[0].config.name -ne "smoke-model") {
        throw "Bootstrap config model name mismatch."
    }

    $registry = Get-Content $registryPath -Raw | ConvertFrom-Json
    if ([string]$registry.models."smoke-model" -ne $modelPath) {
        throw "Bootstrap registry model path mismatch."
    }
}
finally {
    Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Quality smoke checks passed."
