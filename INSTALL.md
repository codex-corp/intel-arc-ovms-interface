# Installation Guide

## 1. Verify the host

```powershell
.\verify_environment.ps1
```

The check reads `settings.json` and `runtime-manifest.json`; it does not require the old `config.env` file.

## 2. Install helper environment and OVMS

```powershell
.\install_all.ps1
```

This creates `.venv`, installs the small helper dependency set, installs the OVMS version pinned in `runtime-manifest.json`, creates the model repository directory, and initializes `config.json` when missing.

## 3. Prepare a model

Preferred path for a Hugging Face model supported by OVMS:

```powershell
.\manage_models.ps1 pull OpenVINO/Qwen3-8B-int4-ov -Name qwen3-8b -Device GPU -CacheSize 2 -MaxNumSeqs 2
```

OVMS owns download and `graph.pbtxt` generation in this flow.

For a model already on disk:

```powershell
.\manage_models.ps1 configure -Path C:\models\my-model -Name my-model -Device GPU
```

## 4. Enable a model

```powershell
.\manage_models.ps1 enable qwen3-8b
```

This uses the native OVMS `--add_to_config` operation against the repository `config.json`.

## 5. Start OVMS

```powershell
.\start_server.ps1
```

The server always starts with `--config_path config.json`; there is no separate standard-vs-dynamic runtime anymore.

Check readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v3/models
```

## 6. Optional compatibility gateway

```powershell
.\run_server.ps1 -Proxy
```

Direct OVMS traffic remains available on port `8000`; the gateway listens on `127.0.0.1:8001` by default and is passthrough unless a compatibility profile is selected.

## Configuration ownership

| File | Responsibility |
|---|---|
| `settings.json` | ports, paths, gateway behavior |
| `runtime-manifest.json` | supported OVMS/runtime version |
| `config.json` | currently enabled OVMS models |
| environment variables | secrets such as `HF_TOKEN` |

`config.env.example` and `Load-Config.ps1` remain only as migration/backward-compatibility aids.
