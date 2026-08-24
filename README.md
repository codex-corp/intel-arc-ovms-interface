# Intel Arc OVMS Interface

Native Windows tooling for running OpenVINO Model Server on Intel Arc GPUs with an OpenAI-compatible API, local model lifecycle commands, and an optional compatibility gateway for IDEs.

## Architecture

```text
PowerShell CLI
   -> OVMS native lifecycle (pull/configure/enable/disable)
      -> config.json
         -> model repository

Client ----------------------> OVMS :8000
Client -> optional gateway --> OVMS :8000
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design details.

## Requirements

- Windows 11
- Intel Arc GPU + current Intel graphics driver
- Python 3.11 for helper/gateway tooling
- OVMS **2026.2** (pinned in `runtime-manifest.json`)

## Install

```powershell
.\install_all.ps1
```

The installer now orchestrates environment checks, the Python helper venv, OVMS installation, and initial `config.json` creation. It no longer downloads a default model or generates MediaPipe graphs itself.

## Model lifecycle

Pull a prepared OpenVINO model through OVMS:

```powershell
.\manage_models.ps1 pull OpenVINO/Qwen3-8B-int4-ov -Name qwen3-8b
```

Enable it in `config.json`:

```powershell
.\manage_models.ps1 enable qwen3-8b
```

Or configure an already-downloaded local model:

```powershell
.\manage_models.ps1 configure -Path C:\models\my-model -Name my-model
```

Other commands:

```powershell
.\manage_models.ps1 status
.\manage_models.ps1 list
.\manage_models.ps1 disable qwen3-8b
.\manage_models.ps1 switch my-model -Path C:\models\my-model
.\manage_models.ps1 rollback
```

`download_model.ps1` remains as a compatibility wrapper around `manage_models.ps1 pull`; the old hard-coded Top 10 model catalog has intentionally been removed so model selection can be redesigned separately.

## Start

```powershell
.\start_server.ps1
```

There is now one server mode: OVMS always starts from `config.json`. `start_server_dynamic.ps1` remains as a deprecated compatibility wrapper.

For the convenience launcher and optional gateway:

```powershell
.\run_server.ps1
.\run_server.ps1 -Proxy
```

## Compatibility gateway

The gateway on port `8001` is optional. Its default profile is `passthrough`, so reasoning and tool-call fields are preserved.

Set `proxy.compatibility_profile` in `settings.json` to:

- `passthrough` — preserve OVMS responses.
- `jetbrains` — add missing stream IDs only.
- `legacy` — old compatibility behavior, including removal of `reasoning_content`.

Telemetry is per request. The gateway reports tokens/sec only when OVMS returns a real `completion_tokens` value; otherwise it reports stream chunks/sec instead of pretending chunks are tokens.

## Configuration

Stable local settings live in `settings.json`. The supported OVMS version lives in `runtime-manifest.json`. `config.json` is the source of truth for models enabled in OVMS. Secrets such as `HF_TOKEN` should be environment variables.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m compileall proxy_server.py tools
```

GitHub Actions also parses every root PowerShell script on `windows-latest`.
