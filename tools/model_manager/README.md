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
- `manage_models.py`: CLI entrypoint.

## Command Surface

PowerShell wrapper at project root:

- `.\manage_models.ps1 status`
- `.\manage_models.ps1 list`
- `.\manage_models.ps1 switch Qwen3-4B`
- `.\manage_models.ps1 switch custom-model --path "g:\ai-hub\llama\models\custom-int4-ov"`
- `.\manage_models.ps1 rollback`

## Notes

- Registry file: `artficats/models_registry.json`
- Swap log file: `artficats/model_swaps.log`
- Backup file: `config.json.bak`
- This tooling assumes OVMS config-reload mode is enabled in your OVMS runtime.

