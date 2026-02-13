#Requires -Version 5.1
<#
.SYNOPSIS
    Loads configuration variables from config.env
.DESCRIPTION
    Reads g:\ai-interface\config.env and sets key-value pairs as global variables.
    Defaults are provided if the file is missing.
#>

$ScriptDir = $PSScriptRoot
$ConfigFile = Join-Path $ScriptDir "config.env"

if (Test-Path $ConfigFile) {
    Get-Content $ConfigFile | Where-Object { $_ -match '=' -and -not $_.StartsWith('#') -and -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object {
        $key, $value = $_ -split '=', 2
        if ($key -and $value) {
            Set-Variable -Name $key.Trim() -Value $value.Trim() -Scope Global
        }
    }
    # Write-Host "  loaded config.env" -ForegroundColor DarkGray
} else {
    Write-Host "⚠️  config.env not found at $ConfigFile" -ForegroundColor Yellow
}

# --- Defaults / Fallbacks ---
if (-not $MODEL_NAME -and $DEFAULT_MODEL_NAME) {
    # Write-Host "  Using Default Model: $DEFAULT_MODEL_NAME" -ForegroundColor DarkGray
    $MODEL_NAME = $DEFAULT_MODEL_NAME
    Set-Variable -Name "MODEL_NAME" -Value $DEFAULT_MODEL_NAME -Scope Global
}
