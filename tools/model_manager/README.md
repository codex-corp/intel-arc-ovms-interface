# Model Manager (Command-Based Hot-Swap Control)

This folder contains a separated, SRP-based implementation for local model control.

## Responsibilities by File

- `env_config.py`: read/update `config.env` safely.
- `file_lock.py`: single-operation lock (`artficats/model_swap.lock`).
- `model_registry.py`: read known model names/paths from registry.
- `ovms_client.py`: probe OVMS `/v3/models` readiness.
- `ovms_config.py`: read/build/write/backup/rollback `config.json`.
- `swap_logger.py`: append JSONL operation logs.
- `swap_service.py`: orchestration layer (status/list/switch/rollback).
- `manage_models.py`: Python CLI entrypoint for the existing hot-swap flow.
- `../../Invoke-OvmsLifecycle.ps1`: native OVMS repository/config lifecycle wrapper.

## Command Surface

Existing hot-swap commands remain unchanged:

- `.\manage_models.ps1 status`
- `.\manage_models.ps1 list`
- `.\manage_models.ps1 switch Qwen3-4B`
- `.\manage_models.ps1 switch custom-model --path "g:\ai-hub\llama\models\custom-int4-ov"`
- `.\manage_models.ps1 rollback`

Native OVMS lifecycle commands are additive:

- `.\manage_models.ps1 native-list`
- `.\manage_models.ps1 pull OpenVINO/Qwen3-4B-int4-ov -Name qwen3-4b`
- `.\manage_models.ps1 configure qwen3-4b -Path ".\models\qwen3-4b"`
- `.\manage_models.ps1 enable qwen3-4b`
- `.\manage_models.ps1 disable qwen3-4b`
- `.\manage_models.ps1 reload`

For text-generation `pull` / `configure`, the existing `Safe`, `Balanced`, and `Fast` performance profiles are supported through `-PerformanceProfile`.

OVMS 2026.x is required for `configure`. The project default is 2026.3. Existing installations can be upgraded explicitly with:

```powershell
.\setup_ovms.ps1 -AutoDownload -Force
```

## Notes

- Registry file: `artficats/models_registry.json`
- Swap log file: `artficats/model_swaps.log`
- Backup file: `config.json.bak`
- Native `pull` / `configure` update the existing registry when a local model path is available.
- Native `enable` / `disable` use OVMS `--add_to_config` / `--remove_from_config` and request runtime config reload when OVMS is already running.
- The original `download_model.ps1` flow is intentionally preserved for backward compatibility.

