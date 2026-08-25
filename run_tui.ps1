#Requires -Version 5.1
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\Load-Config.ps1"

if (-not (Test-Path $PYTHON_EXE)) {
    throw "Python environment not found at '$PYTHON_EXE'. Run install_all.ps1 first."
}

& $PYTHON_EXE -c "import aiohttp, textual" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "TUI dependencies are missing. Install requirements.txt in the project virtual environment."
}

Push-Location $PSScriptRoot
try {
    & $PYTHON_EXE -m tools.tui.app
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
