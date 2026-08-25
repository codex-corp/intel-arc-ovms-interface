from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .env_config import load_env_file, required_value, update_env_file
from .file_lock import FileLock
from .model_registry import load_registry
from .ovms_client import fetch_models, reload_config
from .ovms_config import (
    atomic_write_json,
    backup_config,
    build_swapped_config,
    extract_current_model,
    load_json,
    rollback_config,
)
from .swap_logger import append_event


@dataclass
class ServicePaths:
    root: Path
    env_file: Path
    config_json: Path
    backup_json: Path
    lock_file: Path
    registry_file: Path
    log_file: Path


def make_paths(root: Path) -> ServicePaths:
    artifacts = root / "artficats"
    return ServicePaths(
        root=root,
        env_file=root / "config.env",
        config_json=root / "config.json",
        backup_json=root / "config.json.bak",
        lock_file=artifacts / "model_swap.lock",
        registry_file=artifacts / "models_registry.json",
        log_file=artifacts / "model_swaps.log",
    )


class SwapService:
    def __init__(self, paths: ServicePaths):
        self.paths = paths
        self.env = load_env_file(paths.env_file).values
        self.ovms_port = int(required_value(self.env, "OVMS_PORT", "8000"))

    def list_models(self) -> Dict[str, str]:
        return load_registry(self.paths.registry_file)

    def status(self) -> Dict[str, object]:
        try:
            cfg = load_json(self.paths.config_json)
            current_name, current_path = extract_current_model(cfg)
        except Exception:
            current_name = self.env.get("MODEL_NAME", "")
            current_path = self.env.get("MODEL_PATH", "")

        ovms = fetch_models(self.ovms_port)
        return {
            "configured_model": current_name,
            "configured_path": current_path,
            "ovms_port": self.ovms_port,
            "ovms_reachable": ovms.reachable,
            "ovms_models": ovms.models,
            "ovms_error": ovms.error,
        }

    def switch(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        timeout_sec: int = 120,
        no_wait: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, object]:
        op_id = str(uuid.uuid4())
        registry = self.list_models()
        resolved_path = model_path or registry.get(model_name)
        if not resolved_path:
            raise ValueError(
                f"Unknown model '{model_name}'. Add it to {self.paths.registry_file} or pass --path."
            )
        if not Path(resolved_path).exists():
            raise FileNotFoundError(f"Model path does not exist on disk: {resolved_path}")

        with FileLock(self.paths.lock_file, timeout_sec=15):
            try:
                cfg = load_json(self.paths.config_json)
                current_name, current_path = extract_current_model(cfg)
            except Exception:
                cfg = {}
                current_name = self.env.get("MODEL_NAME", "")
                current_path = self.env.get("MODEL_PATH", "")

            if current_name == model_name and current_path == resolved_path:
                return {
                    "op_id": op_id,
                    "changed": False,
                    "message": f"Model '{model_name}' is already active.",
                    "model_name": model_name,
                    "model_path": resolved_path,
                }

            planned = build_swapped_config(cfg, model_name=model_name, model_path=resolved_path)
            if dry_run:
                return {
                    "op_id": op_id,
                    "changed": False,
                    "dry_run": True,
                    "from_model": current_name,
                    "to_model": model_name,
                    "from_path": current_path,
                    "to_path": resolved_path,
                }

            append_event(
                self.paths.log_file,
                {
                    "op_id": op_id,
                    "event": "swap_started",
                    "from_model": current_name,
                    "to_model": model_name,
                },
            )

            if self.paths.config_json.exists():
                backup_config(self.paths.config_json, self.paths.backup_json)
            atomic_write_json(self.paths.config_json, planned)
            update_env_file(
                self.paths.env_file,
                {"MODEL_NAME": model_name, "MODEL_PATH": resolved_path},
            )

            # Check if OVMS is reachable
            ovms_status = fetch_models(self.ovms_port, timeout_sec=1)
            if not ovms_status.reachable or no_wait:
                append_event(
                    self.paths.log_file,
                    {"op_id": op_id, "event": "swap_applied_offline", "to_model": model_name},
                )
                return {
                    "op_id": op_id,
                    "changed": True,
                    "state": "applied",
                    "message": f"Config updated: {model_name} is set as active model (OVMS offline).",
                    "model_name": model_name,
                    "model_path": resolved_path,
                }

            # OVMS is online: Trigger config reload
            reload_config(self.ovms_port)

            # Wait for model to become ready in OVMS
            wait_timeout = min(timeout_sec, 45)
            ok = self._wait_until_ready(model_name, timeout_sec=wait_timeout)
            if ok:
                append_event(
                    self.paths.log_file,
                    {"op_id": op_id, "event": "swap_ready", "to_model": model_name},
                )
                return {
                    "op_id": op_id,
                    "changed": True,
                    "state": "ready",
                    "message": f"Successfully loaded and verified '{model_name}' in OVMS memory.",
                    "model_name": model_name,
                    "model_path": resolved_path,
                }

            # If reload timed out, rollback
            rollback_config(self.paths.backup_json, self.paths.config_json)
            update_env_file(
                self.paths.env_file,
                {"MODEL_NAME": current_name, "MODEL_PATH": current_path},
            )
            reload_config(self.ovms_port)
            append_event(
                self.paths.log_file,
                {
                    "op_id": op_id,
                    "event": "swap_rolled_back",
                    "to_model": model_name,
                    "reason": "timeout_or_not_ready",
                },
            )
            raise TimeoutError(
                f"Model '{model_name}' was configured, but OVMS did not report it ready within {wait_timeout}s. Rolled back."
            )

    def rollback(self) -> Dict[str, object]:
        if not self.paths.backup_json.exists():
            raise FileNotFoundError(f"No backup found at {self.paths.backup_json}")
        with FileLock(self.paths.lock_file, timeout_sec=15):
            rollback_config(self.paths.backup_json, self.paths.config_json)
            cfg = load_json(self.paths.config_json)
            name, model_path = extract_current_model(cfg)
            update_env_file(self.paths.env_file, {"MODEL_NAME": name, "MODEL_PATH": model_path})
            append_event(self.paths.log_file, {"event": "manual_rollback", "to_model": name})
            return {"rolled_back_to": name, "model_path": model_path}

    def _wait_until_ready(self, model_name: str, timeout_sec: int) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            status = fetch_models(self.ovms_port, timeout_sec=2)
            if status.reachable and model_name in status.models:
                return True
            time.sleep(1)
        return False
