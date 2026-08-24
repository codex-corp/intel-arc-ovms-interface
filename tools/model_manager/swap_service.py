from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from .file_lock import FileLock
from .model_registry import load_registry
from .ovms_client import fetch_models
from .ovms_config import atomic_write_json, backup_config, build_swapped_config, extract_current_model, load_json, rollback_config
from .swap_logger import append_event

@dataclass
class ServicePaths:
    root: Path
    config_json: Path
    backup_json: Path
    lock_file: Path
    registry_file: Path
    log_file: Path

def make_paths(root: Path) -> ServicePaths:
    artifacts = root / "artifacts"
    return ServicePaths(root, root / "config.json", root / "config.json.bak", artifacts / "model_swap.lock", artifacts / "models_registry.json", artifacts / "model_swaps.log")

class SwapService:
    def __init__(self, paths: ServicePaths):
        self.paths = paths
        settings = json.loads((paths.root / "settings.json").read_text(encoding="utf-8"))
        self.ovms_port = int(settings["server"]["rest_port"])

    def list_models(self) -> Dict[str, object]:
        records = load_registry(self.paths.registry_file)
        return {name: {"path": rec.path, "source": rec.source, "task": rec.task, "target_device": rec.target_device, "profile": rec.profile} for name, rec in records.items()}

    def status(self) -> Dict[str, object]:
        ovms = fetch_models(self.ovms_port)
        configured = None
        if self.paths.config_json.exists():
            try:
                name, model_path = extract_current_model(load_json(self.paths.config_json)); configured = {"name": name, "path": model_path}
            except Exception:
                configured = None
        return {"configured_model": configured, "ovms_port": self.ovms_port, "ovms_reachable": ovms.reachable, "ovms_models": ovms.models, "ovms_error": ovms.error}

    def switch(self, model_name: str, model_path: Optional[str] = None, timeout_sec: int = 180, no_wait: bool = False, dry_run: bool = False) -> Dict[str, object]:
        op_id = str(uuid.uuid4()); registry = load_registry(self.paths.registry_file); record = registry.get(model_name)
        resolved_path = model_path or (record.path if record else None)
        if not resolved_path: raise ValueError(f"Unknown model '{model_name}'. Pass --path or add it to {self.paths.registry_file}.")
        if not Path(resolved_path).exists(): raise FileNotFoundError(f"Model path does not exist: {resolved_path}")
        with FileLock(self.paths.lock_file, timeout_sec=15):
            cfg = load_json(self.paths.config_json); current_name = current_path = ""
            try: current_name, current_path = extract_current_model(cfg)
            except Exception: pass
            planned = build_swapped_config(cfg, model_name, resolved_path)
            if dry_run: return {"op_id": op_id, "dry_run": True, "from_model": current_name, "to_model": model_name, "to_path": resolved_path}
            backup_config(self.paths.config_json, self.paths.backup_json); atomic_write_json(self.paths.config_json, planned)
            append_event(self.paths.log_file, {"op_id": op_id, "event": "swap_started", "from_model": current_name, "to_model": model_name})
            if no_wait: return {"op_id": op_id, "changed": True, "state": "applied_no_wait", "model_name": model_name}
            if self._wait_until_ready(model_name, timeout_sec):
                append_event(self.paths.log_file, {"op_id": op_id, "event": "swap_ready", "to_model": model_name}); return {"op_id": op_id, "changed": True, "state": "ready", "model_name": model_name}
            rollback_config(self.paths.backup_json, self.paths.config_json); append_event(self.paths.log_file, {"op_id": op_id, "event": "swap_rolled_back", "to_model": model_name, "reason": "timeout_or_not_ready"})
            raise TimeoutError(f"Model '{model_name}' did not become ready within {timeout_sec}s. Rolled back.")

    def rollback(self) -> Dict[str, object]:
        if not self.paths.backup_json.exists(): raise FileNotFoundError(f"No backup found at {self.paths.backup_json}")
        with FileLock(self.paths.lock_file, timeout_sec=15):
            rollback_config(self.paths.backup_json, self.paths.config_json); name, model_path = extract_current_model(load_json(self.paths.config_json)); append_event(self.paths.log_file, {"event": "manual_rollback", "to_model": name}); return {"rolled_back_to": name, "model_path": model_path}

    def _wait_until_ready(self, model_name: str, timeout_sec: int) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            status = fetch_models(self.ovms_port, timeout_sec=3)
            if status.reachable and model_name in status.models: return True
            time.sleep(2)
        return False
