#Requires -Version 5.1
<#
.SYNOPSIS
    Unified Installer for Intel Arc A750 + OVMS AI Server
.DESCRIPTION
    Automates the entire setup from scratch:
    1. Installs Python 3.11 (if missing)
    2. Creates Virtual Environment
    3. Installs Python dependencies (OpenVINO, Hugging Face, aiohttp)
    4. Downloads Qwen2.5-Coder-7B INT4 model
    5. Downloads and sets up OVMS binary
    6. Generates config files (graph.pbtxt) and launch scripts
#>

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# --- Load Configuration ---
. "$ScriptDir\Load-Config.ps1"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Intel Arc A750 AI Server - Unified Installer" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Using Config:" -ForegroundColor DarkGray
Write-Host "    Install Dir: $AI_INTERFACE_DIR" -ForegroundColor DarkGray
Write-Host "    Model Name:  $MODEL_NAME" -ForegroundColor DarkGray

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Intel Arc A750 AI Server - Unified Installer" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# --- 0. Prerequisites Check ---
Write-Host "Step 0: Checking Prerequisites..." -ForegroundColor White

# OS Version
$os = Get-CimInstance Win32_OperatingSystem
if ([int]$os.BuildNumber -lt 22621) {
    Write-Host "  ⚠️  Windows 11 Build 22621+ required (Current: $($os.BuildNumber))" -ForegroundColor Yellow
} else {
    Write-Host "  ✅ OS: Windows 11 ($($os.BuildNumber))" -ForegroundColor Green
}

# GPU & Driver
$gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "Arc" }
if ($gpu) {
    Write-Host "  ✅ GPU: $($gpu.Name)" -ForegroundColor Green
    try {
        $driverVer = $gpu.DriverVersion
        $driverBuild = [int]($gpu.DriverVersion -split '\.')[-1]
        if ($driverBuild -lt 6078) {
            Write-Host "  ⚠️  Driver build $driverBuild is old. Update to 32.0.101.6078+" -ForegroundColor Yellow
        } else {
            Write-Host "  ✅ Driver: Build $driverBuild" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠️  Could not parse driver version ($($gpu.DriverVersion))" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ❌ No Intel Arc GPU detected!" -ForegroundColor Red
}

# VC++ Redist (Check common registry key for 2015-2022)
if (Test-Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") {
    Write-Host "  ✅ VC++ Redist: Installed" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  VC++ Redistributable (x64) likely missing!" -ForegroundColor Yellow
    Write-Host "      Download: https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor White
}
Write-Host ""

# --- 1. Directory Structure ---
Write-Host "Step 1: Checking Directories..." -ForegroundColor White
New-Item -ItemType Directory -Path $AI_INTERFACE_DIR -Force | Out-Null
New-Item -ItemType Directory -Path "$AI_INTERFACE_DIR\cache" -Force | Out-Null
New-Item -ItemType Directory -Path $MODEL_PATH -Force | Out-Null
New-Item -ItemType Directory -Path $OVMS_DIR -Force | Out-Null
Write-Host "  ✅ Directories ready" -ForegroundColor Green
Write-Host ""

# --- 2. Check Python 3.11 ---
Write-Host "Step 2: Checking Python 3.11..." -ForegroundColor White

$PythonCmd = $null

# 2a. Check 'py' launcher
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $ver = py -3.11 --version 2>&1
    if ($ver -match "3\.11") {
        $PythonCmd = "py -3.11"
        Write-Host "  ✅ Found 'py' launcher: $ver" -ForegroundColor Green
    }
}

# 2b. If not found, check 'python' directly
if (-not $PythonCmd) {
    if (Get-Command "python" -ErrorAction SilentlyContinue) {
        $ver = python --version 2>&1
        if ($ver -match "3\.11") {
            $PythonCmd = "python"
            Write-Host "  ✅ Found 'python' executable: $ver" -ForegroundColor Green
        }
    }
}

# 2c. If still not found, download and install
if (-not $PythonCmd) {
    Write-Host "  ⚠️  Python 3.11 not found. Downloading installer..." -ForegroundColor Yellow
    $installerPath = "$env:TEMP\python-3.11.9-amd64.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $installerPath -UseBasicParsing

    Write-Host "  Installing Python 3.11 (this may take a minute)..." -ForegroundColor Yellow
    Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=1", "Include_pip=1", "TargetDir=$env:LOCALAPPDATA\Programs\Python\Python311" -Wait

    # After install, assume 'py' works or direct path
    $PythonCmd = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    Write-Host "  ✅ Python installed." -ForegroundColor Green
}
Write-Host ""

# --- 3. Virtual Environment ---
Write-Host "Step 3: Setting up Virtual Environment..." -ForegroundColor White
if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    Write-Host "  Creating venv at $VENV_DIR using '$PythonCmd'..." -ForegroundColor DarkGray
    # Execute the command string
    if ($PythonCmd -match "py -3.11") {
        py -3.11 -m venv $VENV_DIR
    } else {
        & $PythonCmd -m venv $VENV_DIR
    }
}
Write-Host "  ✅ Venv ready" -ForegroundColor Green
Write-Host ""

# --- 4. Dependencies ---
Write-Host "Step 4: Installing Dependencies..." -ForegroundColor White
$ReqFile = Join-Path $AI_INTERFACE_DIR "requirements.txt"

if (Test-Path $ReqFile) {
    Write-Host "  Installing from requirements.txt..." -ForegroundColor DarkGray
    & "$VENV_DIR\Scripts\python.exe" -m pip install -r $ReqFile | Out-Null
    Write-Host "  ✅ Dependencies installed (from requirements.txt)" -ForegroundColor Green
} else {
    Write-Host "  requirements.txt not found. Installing manually..." -ForegroundColor Yellow
    & "$VENV_DIR\Scripts\python.exe" -m pip install --upgrade pip openvino huggingface_hub[cli] aiohttp open-interpreter | Out-Null
    Write-Host "  ✅ Dependencies installed (manual list)" -ForegroundColor Green
}
Write-Host ""

# --- 5. Download Model ---
Write-Host "Step 5: Checking Model ($MODEL_NAME)..." -ForegroundColor White
& "$ScriptDir\download_model.ps1"
Write-Host ""

# --- 6. Setup OVMS Binary ---
Write-Host "Step 6: Setting up OVMS Binary..." -ForegroundColor White
if (-not (Test-Path "$OVMS_DIR\ovms.exe")) {
    Write-Host "  Downloading OVMS 2025.4..." -ForegroundColor Yellow
    $zipPath = "$env:TEMP\ovms_windows.zip"
    Invoke-WebRequest -Uri "https://github.com/openvinotoolkit/model_server/releases/download/v2025.4.1/ovms_windows_python_on.zip" -OutFile $zipPath -UseBasicParsing

    # Extract to parent folder because zip contains 'ovms' folder
    $ExtractDir = Split-Path -Path $OVMS_DIR -Parent
    Write-Host "  Extracting to $ExtractDir..." -ForegroundColor Yellow
    Expand-Archive -Path $zipPath -DestinationPath $ExtractDir -Force
    Remove-Item $zipPath
}
Write-Host "  ✅ OVMS binary ready" -ForegroundColor Green
Write-Host ""

# --- 7. Generate Configuration Files ---
Write-Host "Step 7: Generating Configuration Files..." -ForegroundColor White

# 7a. graph.pbtxt
$GraphContent = @'
input_stream: "HTTP_REQUEST_PAYLOAD:input"
output_stream: "HTTP_RESPONSE_PAYLOAD:output"
node: {
  name: "LLMExecutor"
  calculator: "HttpLLMCalculator"
  input_stream: "LOOPBACK:loopback"
  input_stream: "HTTP_REQUEST_PAYLOAD:input"
  input_side_packet: "LLM_NODE_RESOURCES:llm"
  output_stream: "LOOPBACK:loopback"
  output_stream: "HTTP_RESPONSE_PAYLOAD:output"
  input_stream_info: { tag_index: 'LOOPBACK:0', back_edge: true }
  node_options: {
    [type.googleapis.com / mediapipe.LLMCalculatorOptions]: {
      models_path: "./"
      cache_size: 2
      device: "GPU"
      enable_prefix_caching: true
      max_num_seqs: 2
      plugin_config: "{\"KV_CACHE_PRECISION\": \"u8\"}"
    }
  }
  input_stream_handler {
    input_stream_handler: "SyncSetInputStreamHandler",
    options { [mediapipe.SyncSetInputStreamHandlerOptions.ext] { sync_set { tag_index: "LOOPBACK:0" } } }
  }
}
'@
Set-Content -Path "$MODEL_PATH\graph.pbtxt" -Value $GraphContent
Write-Host "  ✅ Created graph.pbtxt" -ForegroundColor Green

# 7b. proxy_server.py (Injects Config Variables)
$ProxyContent = @"
import os
import aiohttp
from aiohttp import web
import json
import uuid
import asyncio

# Config from Env
TARGET_URL = "http://localhost:$OVMS_PORT"
PORT = $PROXY_PORT

async def handle_proxy(request):
    target_path = request.path
    if request.query_string:
        target_path += "?" + request.query_string
    url = f"{TARGET_URL}{target_path}"
    body = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(request.method, url, headers=headers, data=body) as response:
                client_response = web.StreamResponse(status=response.status, reason=response.reason)
                for k, v in response.headers.items():
                    if k.lower() not in ['transfer-encoding', 'content-length']:
                        client_response.headers[k] = v

                is_sse = 'text/event-stream' in response.headers.get('Content-Type', '')
                request_id = f"chatcmpl-{uuid.uuid4()}"
                await client_response.prepare(request)

                if is_sse:
                    async for chunk in response.content:
                        if chunk:
                            try:
                                text = chunk.decode('utf-8')
                                lines = text.split('\n')
                                for line in lines:
                                    if line.startswith('data: ') and line != 'data: [DONE]':
                                        data = json.loads(line[6:])
                                        if 'id' not in data: data['id'] = request_id
                                        await client_response.write(f"data: {json.dumps(data)}\n".encode('utf-8'))
                                    else:
                                        await client_response.write((line + '\n').encode('utf-8'))
                            except: await client_response.write(chunk)
                else:
                    async for chunk in response.content: await client_response.write(chunk)
                return client_response
        except Exception as e: return web.Response(text=str(e), status=500)

app = web.Application()
app.router.add_route('*', '/{path_info:.*}', handle_proxy)

if __name__ == '__main__':
    print(f"🚀 Proxy running on port {PORT} -> {TARGET_URL}")
    web.run_app(app, port=PORT)
"@
Set-Content -Path $PROXY_SCRIPT -Value $ProxyContent
Write-Host "  ✅ Created proxy_server.py (Configured for Port $PROXY_PORT -> $OVMS_PORT)" -ForegroundColor Green

# 7c. start_server.ps1 (Injects Config Variables)
$StartScript = @"
#Requires -Version 5.1
param([switch]`$VerboseOutput)
`$ScriptDir = `$PSScriptRoot
. "`$ScriptDir\Load-Config.ps1"

`$LogLevel = "ERROR"
if (`$VerboseOutput) { `$LogLevel = "INFO" }

Write-Host "🚀 Launching OVMS (`$MODEL_NAME)..." -ForegroundColor Cyan
Write-Host "   Log Level: `$LogLevel" -ForegroundColor DarkGray
cmd /c "cd /d `"`$OVMS_DIR`" && setupvars.bat > NUL 2>&1 && ovms.exe --model_name `$MODEL_NAME --model_path `"`$MODEL_PATH`" --port `$OVMS_GRPC_PORT --rest_port `$OVMS_PORT --log_level `$LogLevel"
"@
Set-Content -Path "$AI_INTERFACE_DIR\start_server.ps1" -Value $StartScript
Write-Host "  ✅ Created start_server.ps1" -ForegroundColor Green

$IdeScript = @"
#Requires -Version 5.1
`$ScriptDir = `$PSScriptRoot
. "`$ScriptDir\Load-Config.ps1"

`$ErrorActionPreference = "Stop"
`$MaxRetries = 10
`$RetryCount = 0

Write-Host "⏳ Waiting for OVMS (`$OVMS_PORT)..." -ForegroundColor Yellow

do {
    if (Test-NetConnection -ComputerName localhost -Port `$OVMS_PORT -InformationLevel Quiet -ErrorAction SilentlyContinue -WarningAction SilentlyContinue) {
        Write-Host "✅ OVMS is UP!" -ForegroundColor Green
        Write-Host "🚀 Starting IDE Proxy on port `$PROXY_PORT..." -ForegroundColor Cyan
        & `$PYTHON_EXE `$PROXY_SCRIPT
        exit 0
    }
    `$RetryCount++
    Start-Sleep -Seconds 3
    Write-Host "." -NoNewline -ForegroundColor DarkGray
} while (`$RetryCount -lt `$MaxRetries)

Write-Host ""
Write-Host "❌ OVMS did not start within 30 seconds. Run .\start_server.ps1 first." -ForegroundColor Red
exit 1
"@
Set-Content -Path "$AI_INTERFACE_DIR\run_ide_proxy.ps1" -Value $IdeScript
Write-Host "  ✅ Created run_ide_proxy.ps1" -ForegroundColor Green
Write-Host ""

# --- Done ---
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the server:"
Write-Host "  1. .\start_server.ps1      (Main Inference Server)"
Write-Host "  2. .\run_ide_proxy.ps1     (Optional: For PhpStorm/IDE compatibility)"
Write-Host ""
