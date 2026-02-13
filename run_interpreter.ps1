#Requires -Version 5.1
<#
.SYNOPSIS
    Runs Open Interpreter with the local OVMS server (Qwen2.5-Coder-7B)
.DESCRIPTION
    Activates the .venv and launches interpreter with correct API settings.
    Usage: .\run_interpreter.ps1 [prompt]
#>

param(
    [string]$Prompt
)

$ScriptDir = $PSScriptRoot
. "$ScriptDir\Load-Config.ps1"

$VenvScript = "$VENV_DIR\Scripts\interpreter.exe"
$ApiBase = "http://localhost:$OVMS_PORT/v3"
$ModelName = $MODEL_NAME
$ApiKey = "sk-dummy"

if (-not (Test-Path $VenvScript)) {
    Write-Host "Error: Interpreter not found at $VenvScript" -ForegroundColor Red
    Write-Host "Run: pip install open-interpreter" -ForegroundColor Yellow
    exit 1
}

# Check if server is running
if (-not (Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet -ErrorAction SilentlyContinue)) {
    Write-Host "Warning: OVMS server (port 8000) not detected." -ForegroundColor Yellow
    Write-Host "Make sure to run start_server.ps1 first." -ForegroundColor split
}

if ($Prompt) {
    # Run in non-interactive mode with prompt via pipe (workaround for some CLI issues)
    # Note: simple piping might not handle complex interactions, but starts the conversation.
    # Actually, let's just pass it as an argument if supported, or launch interactive if not.
    # The user can just run: .\run_interpreter.ps1 "Do X"

    # Try passing as argument (interpreter <prompt>)
    & $VenvScript --api_base $ApiBase --model $ModelName --api_key $ApiKey $Prompt
}
else {
    # Interactive mode
    & $VenvScript --api_base $ApiBase --model $ModelName --api_key $ApiKey
}
