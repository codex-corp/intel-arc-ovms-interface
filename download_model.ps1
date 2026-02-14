#Requires -Version 5.1
<#
.SYNOPSIS
    Downloads OpenVINO IR INT4 models for Arc A750
.DESCRIPTION
    Standard mode: Downloads the model defined in config.env.
    Setup mode (-Setup): Displays a menu of top 10 models, updates config.env, and downloads.
#>
param (
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# --- Load Configuration ---
. "$ScriptDir\Load-Config.ps1"

# Top 10 OpenVINO INT4 Models (Arc A750 16GB VRAM / 80GB RAM)
$Models = @(
    @{ Name = "Qwen2.5-Coder-7B-Instruct"; ID = "OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov"; Size = "~5 GB"; Desc = "Best for Coding (Default)" },
    @{ Name = "Qwen3-8B"; ID = "OpenVINO/Qwen3-8B-int4-ov"; Size = "~5 GB"; Desc = "Latest Qwen3, Strong All-Round" },
    @{ Name = "Qwen3-4B"; ID = "OpenVINO/Qwen3-4B-int4-ov"; Size = "~3 GB"; Desc = "Fast Qwen3, Great Quality/Speed" },
    @{ Name = "Qwen3-14B"; ID = "OpenVINO/Qwen3-14B-int4-ov"; Size = "~8 GB"; Desc = "Largest Qwen3, Best Quality" },
    @{ Name = "DeepSeek-R1-Distill-7B"; ID = "OpenVINO/DeepSeek-R1-Distill-Qwen-7B-int4-ov"; Size = "~5 GB"; Desc = "DeepSeek R1 Reasoning" },
    @{ Name = "DeepSeek-R1-Distill-14B"; ID = "OpenVINO/DeepSeek-R1-Distill-Qwen-14B-int4-ov"; Size = "~8 GB"; Desc = "DeepSeek R1 Reasoning, Larger" },
    @{ Name = "Phi-4-mini-instruct"; ID = "OpenVINO/Phi-4-mini-instruct-int4-ov"; Size = "~5 GB"; Desc = "Microsoft Phi-4 Mini" },
    @{ Name = "Phi-4"; ID = "OpenVINO/phi-4-int4-ov"; Size = "~8 GB"; Desc = "Microsoft Phi-4 Full (14B)" },
    @{ Name = "Mixtral-8x7B-Instruct"; ID = "OpenVINO/mixtral-8x7b-instruct-v0.1-int4-ov"; Size = "~24 GB"; Desc = "MoE ⚠️ Needs CPU offload" },
    @{ Name = "Qwen3-1.7B"; ID = "OpenVINO/Qwen3-1.7B-int4-ov"; Size = "~1.2 GB"; Desc = "Ultra-Fast Debug & Testing" }
)

# --- Interactive Setup Mode ---
if ($Setup) {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  Select Model to Install (INT4 Optimized)" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""

    for ($i = 0; $i -lt $Models.Count; $i++) {
        $m = $Models[$i]
        Write-Host "  [$($i+1)] $($m.Name.PadRight(25)) | $($m.Size.PadRight(8)) | $($m.Desc)" -ForegroundColor White
    }
    Write-Host ""

    $selection = Read-Host "  Enter number (1-$($Models.Count)) or 'c' to cancel"
    if ($selection -match '^\d+$' -and [int]$selection -ge 1 -and [int]$selection -le $Models.Count) {
        $selectedModel = $Models[[int]$selection - 1]

        # Construct new path (replace old model name in path)
        # Assumes standard structure: ...\models\<name>-int4-ov
        $newName = $selectedModel.ID.Split('/')[-1].Replace("OpenVINO/", "")
        $newPath = Join-Path "$AI_HUB_DIR\llama\models" $newName

        Write-Host ""
        Write-Host "  Updating config.env..." -ForegroundColor Yellow
        Write-Host "    MODEL_NAME = $($selectedModel.Name)" -ForegroundColor DarkGray
        Write-Host "    MODEL_PATH = $newPath" -ForegroundColor DarkGray

        # Update config.env
        $ConfigFile = "$ScriptDir\config.env"
        $content = Get-Content $ConfigFile
        $newContent = @()
        foreach ($line in $content) {
            if ($line -match "^MODEL_NAME=") { $newContent += "MODEL_NAME=$($selectedModel.Name)" }
            elseif ($line -match "^MODEL_PATH=") { $newContent += "MODEL_PATH=$newPath" }
            else { $newContent += $line }
        }
        $newContent | Set-Content $ConfigFile

        # Reload Config to apply changes to current session
        . "$ScriptDir\Load-Config.ps1"

        Write-Host "  ✅ Configuration updated!" -ForegroundColor Green
    }
    elseif ($selection -eq 'c') {
        Write-Host "  Setup cancelled." -ForegroundColor Yellow
        exit
    }
    else {
        Write-Host "  Invalid selection." -ForegroundColor Red
        exit 1
    }
}

# --- Download Logic ---
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Downloading: $MODEL_NAME" -ForegroundColor Cyan
Write-Host "  Target:      $MODEL_PATH" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Determine Model ID (Reverse lookup or guess from config)
$known = $Models | Where-Object { $_.Name -eq $MODEL_NAME }
if ($known) {
    $ModelId = $known.ID
}
else {
    # Fallback: Check if MODEL_NAME looks like an ID, otherwise warn
    # Assuming config might have full ID or short name. For now, trust config triggers correct path.
    # Actually, huggingface-cli needs the repo ID.
    # If standard config only has "qwen2.5-coder-7b", we need the Repo ID.
    # The config.env MODEL_NAME is "qwen2.5-coder-7b".
    # The config.env doesn't store the HF Repo ID, only the usage name.
    # This is a bit risky if config has custom model.
    # But for this script, we can default to Qwen if not found in list, or user must manually set.

    if ($MODEL_NAME -eq "qwen2.5-coder-7b") {
        $ModelId = "OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov"
    }
    else {
        # Try to find match in list by Name
        Write-Host "⚠️  Unknown model name in config: $MODEL_NAME" -ForegroundColor Yellow
        Write-Host "   Assuming it is a valid huggingface repo ID or you manually handle it." -ForegroundColor Yellow
        $ModelId = $MODEL_NAME # Hope user put full ID in config if using custom
    }
}

Write-Host "  Repo ID: $ModelId" -ForegroundColor DarkGray

# Check huggingface-cli
try {
    $hfVer = huggingface-cli --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Not found" }
}
catch {
    Write-Host "  ⚠️  huggingface-cli not found. Installing..." -ForegroundColor Yellow
    pip install --upgrade huggingface_hub[cli]
}

Write-Host "  Downloading..." -ForegroundColor Yellow
huggingface-cli download $ModelId --local-dir $MODEL_PATH

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "  ✅ Download complete!" -ForegroundColor Green

    # --- Auto-Generate graph.pbtxt based on model size tier ---
    # Tiers: Small (≤3GB) / Medium (≤5GB) / Large (8GB+) / MoE (CPU offload)
    $GraphPath = Join-Path $MODEL_PATH "graph.pbtxt"

    # Determine tier from selected model or size string
    $sizeStr = ""
    $isMoE = $false
    if ($known) {
        $sizeStr = $known.Size
        if ($known.Desc -match "MoE") { $isMoE = $true }
    }

    # Parse approximate GB from size string like "~5 GB"
    $sizeGb = 5  # default
    if ($sizeStr -match '~?(\d+\.?\d*)') { $sizeGb = [double]$Matches[1] }

    if ($isMoE) {
        # MoE: use AUTO device for CPU+GPU, conservative cache
        $device = "AUTO"
        $cacheSize = 2
        $maxSeqs = 2
        $pluginCfg = '"{\"KV_CACHE_PRECISION\": \"u8\"}"'
        $tierLabel = "MoE (AUTO: GPU+CPU offload)"
    }
    elseif ($sizeGb -le 3) {
        # Small models: plenty of VRAM headroom
        $device = "GPU"
        $cacheSize = 10
        $maxSeqs = 8
        $pluginCfg = '"{\"KV_CACHE_PRECISION\": \"u8\"}"'
        $tierLabel = "Small (high throughput)"
    }
    elseif ($sizeGb -le 5) {
        # Medium models: balanced
        $device = "GPU"
        $cacheSize = 4
        $maxSeqs = 4
        $pluginCfg = '"{\"KV_CACHE_PRECISION\": \"u8\"}"'
        $tierLabel = "Medium (balanced)"
    }
    else {
        # Large models: conservative to fit in 16GB
        $device = "GPU"
        $cacheSize = 2
        $maxSeqs = 2
        $pluginCfg = '"{\"KV_CACHE_PRECISION\": \"u8\"}"'
        $tierLabel = "Large (conservative)"
    }

    Write-Host "  Generating graph.pbtxt [$tierLabel]..." -ForegroundColor Yellow
    Write-Host "    device=$device  cache_size=$cacheSize  max_num_seqs=$maxSeqs" -ForegroundColor DarkGray

    $GraphContent = @"
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
      cache_size: $cacheSize
      device: "$device"
      enable_prefix_caching: true
      max_num_seqs: $maxSeqs
      plugin_config: $pluginCfg
    }
  }
  input_stream_handler {
    input_stream_handler: "SyncSetInputStreamHandler",
    options { [mediapipe.SyncSetInputStreamHandlerOptions.ext] { sync_set { tag_index: "LOOPBACK:0" } } }
  }
}
"@
    Set-Content -Path $GraphPath -Value $GraphContent
    Write-Host "  ✅ Created graph.pbtxt" -ForegroundColor Green

    Write-Host ""
    Write-Host "  🚀 Model Ready! Run '.\install_all.ps1' or '.\start_server.ps1' to launch." -ForegroundColor Green
}
else {
    Write-Host "  ❌ Download failed." -ForegroundColor Red
}
Write-Host ""
