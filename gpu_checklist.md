# GPU Verification Checklist — Intel Arc A750

Use this checklist to confirm the Intel Arc A750 is **actually** running inference via XMX engines (not falling back to CPU).

---

## ✅ Pre-Launch Checks

- [ ] **Driver version** ≥ `32.0.101.6078` — verify with `verify_environment.ps1`
- [ ] **ReBAR enabled** in BIOS (`Above 4G Decoding` + `Re-Size BAR Support`)
- [ ] **OpenVINO sees GPU** — run:
  ```powershell
  python -c "import openvino as ov; core = ov.Core(); print(core.available_devices); print(core.get_property('GPU', 'FULL_DEVICE_NAME'))"
  ```
  **Expected:** `['CPU', 'GPU']` and `Intel(R) Arc(TM) A750 Graphics`

---

## ✅ OVMS Startup Log Verification

After running `start_server.ps1`, look for these lines in the console output:

| What to look for | Healthy value | Problem |
|---|---|---|
| `Device:` | `INTEL_GPU.0` | `CPU` = wrong device |
| `Full Name:` | `Intel(R) Arc(TM) A750 Graphics` | `UHD Graphics` = using iGPU |
| Plugin loaded | `INTEL_GPU` | No mention = driver issue |

**If you see `CPU` instead of `INTEL_GPU.0`:** Stop the server and fix driver/runtime before proceeding.

---

## ✅ Runtime Verification with xpu-smi

### Install
Download from: [Intel XPU Manager](https://github.com/intel/xpumanager/releases)

### Monitor During Inference
Open a **second PowerShell window** and run:

```powershell
xpu-smi.exe dump -d 0 -m 1,2,24,25
```

| Metric ID | Name | Healthy During Inference |
|---|---|---|
| 1 | GPU Utilization (%) | 50–100% during prefill |
| 2 | EU Active (%) | > 0% during generation |
| 24 | GPU Memory Used (MB) | 5000–7500 MB |
| 25 | GPU Memory Bandwidth (%) | > 0% |

### Send a Test Request
While xpu-smi is monitoring, send an inference request from a **third terminal**:

```powershell
curl -X POST http://localhost:8000/v3/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"qwen2.5-coder-7b","messages":[{"role":"user","content":"Write a PHP function to validate email"}],"max_tokens":200}'
```

---

## ✅ Task Manager Verification

1. Open **Task Manager** → **Performance** tab
2. Find the **Intel Arc A750** GPU (not the integrated GPU)
3. During inference:
   - **Dedicated GPU memory** should rise to **~6–7 GB**
   - **GPU utilization** should spike during prompt prefill
   - **System RAM** should **NOT** jump to 50+ GB (WDDM spill indicator)

---

## ✅ Quick Health Summary

| Indicator | ✅ Healthy | ❌ Problem |
|---|---|---|
| Dedicated GPU VRAM | 5–7.5 GB used | < 1 GB or 0 = CPU fallback |
| System RAM | Stable (normal usage) | Spikes 30–60+ GB = WDDM spill |
| Token speed | ~10–20 tok/s | < 1 tok/s = CPU or spill |
| xpu-smi EU Active | > 0% during generation | 0% = model not on GPU |
| OVMS log device | `INTEL_GPU.0` | `CPU` = wrong target |
