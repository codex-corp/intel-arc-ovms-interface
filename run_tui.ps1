#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

. "$PSScriptRoot\Load-Config.ps1"

if (-not (Test-Path $PYTHON_EXE)) {
    throw "Python environment not found at '$PYTHON_EXE'. Run install_all.ps1 first."
}

& $PYTHON_EXE -c "import aiohttp, textual" 2>$null
if ($LASTEXITCODE -ne 0) {
    $TuiRequirements = Join-Path $PSScriptRoot "requirements-tui.txt"
    if (-not (Test-Path $TuiRequirements)) {
        throw "TUI dependencies are missing and requirements-tui.txt was not found."
    }

    Write-Host "Installing TUI dependencies..." -ForegroundColor Cyan
    & $PYTHON_EXE -m pip install -r $TuiRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install TUI dependencies."
    }
}

Push-Location $PSScriptRoot
try {
    & $PYTHON_EXE -m tools.tui.app
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
