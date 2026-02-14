# Installation Guide — Intel Arc A750 OVMS Inference Server

> **Native Windows 11 — No WSL, No Docker**
> Last updated: 2026-02-14

---

## Architecture

```
Intel Arc A750 (GPU, Level Zero → XMX)
        ↓
OpenVINO 2025.4 (GPU plugin)
        ↓
OVMS (Windows native binary)
        ↓  REST :8000
IDE / Tools (PHPStorm, opencode, etc.)
```

---

## Prerequisites

| Requirement | Minimum | Verified |
|---|---|---|
| OS | Windows 11 22H2+ | Build 26200 ✅ |
| GPU | Intel Arc A750 | Detected ✅ |
| Driver | ≥ 32.0.101.6078 | 32.0.101.8425 ✅ |
| ReBAR | Enabled in BIOS | Check BIOS ⚠️ |
| VC++ Redist | 2015–2022 (x64) | v14.44 ✅ |
| Python | 3.10–3.12 | 3.11.9 ✅ |

### BIOS Settings (Critical)

1. **Above 4G Decoding** → Enabled
2. **Re-Size BAR Support** → Enabled

> Without ReBAR, Arc GPU performance drops ~40% and may cause random inference crashes.

### Intel Driver

Install the **generic** Intel Arc driver from [intel.com](https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html) — do NOT rely on Windows Update.

### VC++ Redistributable

Download if missing: [https://aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

## Step 1 — Install Python 3.11

OpenVINO 2025.x requires Python 3.10–3.12. If you only have 3.13+:

```powershell
# Download Python 3.11.9 installer
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
  -OutFile "$env:TEMP\python-3.11.9-amd64.exe" -UseBasicParsing

# Silent install (user-level, no PATH modification)
Start-Process -FilePath "$env:TEMP\python-3.11.9-amd64.exe" `
  -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", `
    "Include_launcher=1", "Include_pip=1", `
    "TargetDir=$env:LOCALAPPDATA\Programs\Python\Python311" `
  -Wait

# Verify
py --list
# Expected: -V:3.11  Python 3.11 (64-bit)
```

---

## Step 2 — Create Virtual Environment

```powershell
py -3.11 -m venv "g:\ai-interface\.venv"
```

---

## Step 3 — Install OpenVINO & Tools

```powershell
& "g:\ai-interface\.venv\Scripts\python.exe" -m pip install --upgrade pip openvino huggingface_hub[cli]
```

### Verify GPU Detection

```powershell
& "g:\ai-interface\.venv\Scripts\python.exe" -c @"
import openvino as ov
core = ov.Core()
print('OpenVINO:', ov.__version__)
print('Devices:', core.available_devices)
if 'GPU' in core.available_devices:
    print('GPU:', core.get_property('GPU', 'FULL_DEVICE_NAME'))
"@
```

**Expected output:**

```
OpenVINO: 2025.4.1-20426
Devices: ['CPU', 'GPU']
GPU: Intel(R) Arc(TM) A750 Graphics (dGPU)
```

---

## Step 4 — Download the Model

Recommended helper (uses Python API download + graph generation):

```powershell
.\download_model.ps1 -Setup -PerformanceProfile Balanced
```

Or direct Python API command:

```powershell
& "g:\ai-interface\.venv\Scripts\python.exe" -c "from huggingface_hub import snapshot_download; snapshot_download('OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov', local_dir=r'g:\ai-hub\llama\models\qwen-int4-ov')"
```

Optional CLI fallback (if available on your machine):

```powershell
& "g:\ai-interface\.venv\Scripts\huggingface-cli.exe" download `
  OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov `
  --local-dir "g:\ai-hub\llama\models\qwen-int4-ov"
```

> ~5 GB download. The model folder should contain `openvino_model.xml`, `openvino_model.bin`, and tokenizer files.

### Performance Profile Notes

`download_model.ps1` supports:
- `-PerformanceProfile Safe` (`cache_size=2`, `max_num_seqs=2`)
- `-PerformanceProfile Balanced` (`cache_size=4`, `max_num_seqs=4`) **default**
- `-PerformanceProfile Fast` (`cache_size=8`, `max_num_seqs=8`, may OOM on larger models)

---

## Step 5 — Download OVMS Binary

We use the **Windows native (legacy)** binary.

### Option A: Helper Script
```powershell
.\setup_ovms.ps1
```

### Option B: Manual Commands
If the script fails, run these commands manually:

```powershell
# 1. Create directory
New-Item -ItemType Directory -Path "g:\ai-interface\ovms" -Force

# 2. Download ZIP (v2025.4.1)
Invoke-WebRequest -Uri "https://github.com/openvinotoolkit/model_server/releases/download/v2025.4.1/ovms_windows_python_on.zip" `
  -OutFile "$env:TEMP\ovms_windows.zip" -UseBasicParsing

# 3. Extract
Expand-Archive -Path "$env:TEMP\ovms_windows.zip" -DestinationPath "g:\ai-interface\ovms" -Force

# 4. Verify contents (ovms.exe)
Get-ChildItem "g:\ai-interface\ovms\ovms" | Select-Object Name, Length
```

---

## Step 6 — Configure LLM Graph

LLMs in OVMS use a MediaPipe graph. Create `g:\ai-hub\llama\models\qwen-int4-ov\graph.pbtxt`:

```text
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
  input_stream_info: {
    tag_index: 'LOOPBACK:0',
    back_edge: true
  }
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
    options {
      [mediapipe.SyncSetInputStreamHandlerOptions.ext] {
        sync_set {
          tag_index: "LOOPBACK:0"
        }
      }
    }
  }
}
```

## Step 7 — Start the Server

### Option A — Standard (single model from `MODEL_NAME` / `MODEL_PATH`)

```powershell
.\start_server.ps1
```

### Option B — Dynamic (hot-swap friendly, recommended with `manage_models.ps1`)

```powershell
.\start_server_dynamic.ps1
```

In dynamic mode, OVMS reads `config.json` (`--config_path`) and can be controlled by:

```powershell
.\manage_models.ps1 status
.\manage_models.ps1 switch Qwen3-4B
.\manage_models.ps1 rollback
```

Manual standard command (requires `setupvars.bat` to set DLL paths):

```powershell
cmd /c "cd /d g:\ai-interface\ovms\ovms && setupvars.bat && ovms.exe --model_name qwen2.5-coder-7b --model_path g:\ai-hub\llama\models\qwen-int4-ov --port 9000 --rest_port 8000"
```

### Verify Startup Logs

Look for:

```
OpenVINO Model Server 2025.4.1...
Status change to: AVAILABLE
```

---

## Step 8 — Test the API

```powershell
# Create a test JSON file (to avoid shell escaping issues)
Set-Content test.json '{"model":"qwen2.5-coder-7b","messages":[{"role":"user","content":"Hello!"}],"max_tokens":100}'

# Chat completion
curl -X POST http://localhost:8000/v3/chat/completions `
  -H "Content-Type: application/json" `
  -d @test.json
```

---

## Configuration Reference

### graph.pbtxt (LLM Calculator Options)

| Key | Value | Purpose |
|---|---|---|
| `models_path` | `./` | Path to model files (relative to where graph.pbtxt is) |
| `device` | `GPU` | Routes to Arc A750 via Level Zero |
| `cache_size` | `2` | 2 GB KV cache limit (critical for 8GB VRAM) |
| `enable_prefix_caching` | `true` | Reuses KV cache for multi-turn chat |
| `plugin_config` | `{"KV_CACHE_PRECISION": "u8"}` | Cuts KV cache usage by 50% |
| `max_num_seqs` | `2` | Limits concurrent requests to prevent OOM |

---

## Memory Budget (8 GB VRAM)

| Component | Size |
|---|---|
| Weights (INT4) | ~4.8 GB |
| Runtime overhead | ~1.2 GB |
| KV cache (4k ctx, u8) | ~0.75 GB |
| WDDM desktop reserve | ~0.8 GB |
| **Total** | **~7.55 GB** ✅ |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `CPU` in OVMS logs instead of `INTEL_GPU` | Reinstall Intel driver from intel.com (not Windows Update) |
| System RAM spikes to 50+ GB | WDDM spill — ensure `KV_CACHE_PRECISION: u8`, cap context to 2048 |
| Token speed < 1 tok/s | Model spilled to system RAM — reduce context or switch to 3B model |
| OpenVINO can't find GPU | Check driver version ≥ 6078, enable ReBAR in BIOS |
| `ModuleNotFoundError: openvino` | Activate the venv first: `.venv\Scripts\Activate.ps1` |

Full troubleshooting guide: [oom_troubleshooting.md](oom_troubleshooting.md)

---

## File Reference

| File | Purpose |
|---|---|
| `verify_environment.ps1` | Check all prerequisites |
| `download_model.ps1` | Download INT4 model from Hugging Face |
| `setup_ovms.ps1` | Download/extract OVMS binary |
| `config.json` | OVMS model server configuration |
| `start_server.ps1` | Launch OVMS inference server |
| `start_server_dynamic.ps1` | Launch OVMS in `--config_path` dynamic mode |
| `manage_models.ps1` | Command-based model switching (`status/list/switch/rollback`) |
| `gpu_checklist.md` | GPU verification checklist |
| `oom_troubleshooting.md` | OOM/WDDM spill mitigation guide |

---

## Locked Stack

| Layer | Choice |
|---|---|
| OS | Windows 11 (native) |
| GPU | Intel Arc A750 (8 GB) |
| Runtime | OpenVINO 2025.4 GPU plugin |
| Server | OVMS (Windows native binary) |
| Model | Qwen2.5-Coder-7B INT4 (OpenVINO IR) |
| API | `/v3/chat/completions` (`:8000`) |
| Python | 3.11.9 (venv) |


