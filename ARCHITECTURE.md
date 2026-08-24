# Architecture

## Principles

- `settings.json` contains stable local runtime settings; secrets remain environment variables.
- `runtime-manifest.json` pins the supported OVMS release in one place.
- `config.json` is the source of truth for enabled/served models.
- OVMS owns model pull/configure operations; this project wraps the native CLI instead of generating `graph.pbtxt` itself.
- The compatibility gateway is optional and passthrough by default.
- Telemetry is per request; SSE chunks are never reported as tokens unless OVMS returns token usage.

## Runtime flow

```text
PowerShell CLI
  -> model/runtime manager
     -> OVMS native CLI / config.json
        -> model repository

Client -> OVMS :8000
Client -> optional gateway :8001 -> OVMS :8000
```

## Model lifecycle

```powershell
.\manage_models.ps1 pull OpenVINO/<model> -Name my-model
.\manage_models.ps1 enable my-model
.\start_server.ps1
.\manage_models.ps1 status
.\manage_models.ps1 disable my-model
```

`switch`/`rollback` remain available for compatibility with the previous single-active-model flow.
