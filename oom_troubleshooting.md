# OOM & WDDM Spill Troubleshooting — Intel Arc A750 (8GB)

When the model + KV cache exceeds ~7.2 GB of VRAM, Windows WDDM will "spill" into system RAM, causing catastrophic performance loss. Follow these escalating steps to fix it.

---

## 🔍 How to Detect a WDDM Spill

| Symptom | Cause |
|---|---|
| System RAM jumps to 30–60+ GB | Model weights being buffered in Shared GPU Memory |
| Token speed drops to < 1 tok/s | Data shuttling across PCIe instead of staying in VRAM |
| Task Manager shows low Dedicated GPU memory | Model failed to load on GPU |
| OVMS logs show timeout/hang | KV cache overflowed VRAM |

---

## 🛠️ Mitigation Steps (Escalating)

### Level 1: Verify Basics
```powershell
# Confirm GPU is being used (not CPU fallback)
python -c "import openvino as ov; print(ov.Core().get_property('GPU', 'FULL_DEVICE_NAME'))"
```
- Must show `Intel(R) Arc(TM) A750 Graphics`

### Level 2: Reduce KV Cache
Ensure `config.json` has:
```json
"KV_CACHE_PRECISION": "u8"
```
This cuts KV cache size by ~50% compared to FP16 default.

### Level 3: Cap Context Length
If using long prompts, limit context to 2048 tokens:
```json
"plugin_config": {
    "KV_CACHE_PRECISION": "u8",
    "MAX_NUM_BATCHED_TOKENS": "2048"
}
```

### Level 4: Enable Memory Statistics
Add to `plugin_config` in `config.json`:
```json
"GPU_MEMORY_STATISTICS": "1"
```
This logs exact VRAM usage breakdown in the OVMS console — helps pinpoint what's consuming memory.

### Level 5: Disable Dynamic Quantization Overhead
Already in `start_server.ps1`:
```
--plugin_config '{"DYNAMIC_QUANTIZATION_GROUP_SIZE": "0"}'
```
Saves a few hundred MB of activation memory.

### Level 6: Use Smaller Quantization
If the model still doesn't fit, download a more aggressive quantization:
```powershell
# Option A: Try channel-wise INT4 (slightly smaller)
optimum-cli export openvino -m Qwen/Qwen2.5-Coder-7B-Instruct `
    --weight-format int4 --group-size -1 --ratio 1.0 `
    g:\ai-hub\llama\models\qwen-int4-ov-slim
```

### Level 7: Nuclear — Switch to 3B Model
If 7B simply cannot fit with your workload:
```powershell
huggingface-cli download OpenVINO/Phi-3.5-mini-instruct-int4-ov `
    --local-dir g:\ai-hub\llama\models\phi-3.5-mini-int4-ov
```
Update `config.json` base_path accordingly. Phi-3.5-mini INT4 uses only ~2.3 GB VRAM.

---

## 📊 Memory Budget Reference

| Component | FP16 Default | With u8 KV |
|---|---|---|
| Weights (INT4) | ~4.8 GB | ~4.8 GB |
| Runtime overhead | ~1.2 GB | ~1.2 GB |
| KV Cache (4k ctx) | ~1.5 GB | **~0.75 GB** |
| WDDM desktop reserve | ~0.8 GB | ~0.8 GB |
| **Total** | **~8.3 GB** ❌ spill | **~7.55 GB** ✅ fits |

---

## ⚡ Emergency Recovery

If the server hangs or system becomes unresponsive:

```powershell
# Kill OVMS process
Stop-Process -Name "ovms" -Force -ErrorAction SilentlyContinue

# Clear GPU cache
Remove-Item "g:\ai-interface\cache\*" -Recurse -Force -ErrorAction SilentlyContinue
```

Then restart with reduced context (`MAX_NUM_BATCHED_TOKENS: 2048`).
