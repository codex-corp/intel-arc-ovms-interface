from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.core.config import RuntimeConfig
from tools.core.config_engine import (
    atomic_write_json,
    backup_config,
    build_swapped_config,
    disable_model_in_config,
    enable_model_in_config,
    extract_current_model,
    get_all_configured_models,
    load_json,
    rollback_config,
)
from tools.core.env_resolver import resolve_ovms_environment
from tools.core.manifest import is_model_weights_ready, load_manifest
from tools.core.readiness import probe_ovms_readiness, wait_for_ovms_ready
from tools.model_manager.env_config import update_env_file
from tools.model_manager.model_registry import load_registry
from tools.model_manager.ovms_client import reload_config


def run_ovms_cli(
    config: RuntimeConfig,
    args: List[str],
    timeout_sec: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Executes the native OVMS 2026.3 CLI binary with cached setupvars environment."""
    ovms_exe = config.ovms_dir / "ovms.exe"
    if not ovms_exe.exists():
        raise FileNotFoundError(f"OVMS binary not found at: {ovms_exe}")

    env = resolve_ovms_environment(config.ovms_dir)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    return subprocess.run(
        [str(ovms_exe)] + args,
        cwd=str(config.root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        creationflags=creationflags,
    )


class OvmsLifecycleService:
    """Sole authority for OVMS model lifecycle, configuration mutations, and hot-swapping."""

    def __init__(self, config: RuntimeConfig):
        self.config = config

    def status(self) -> Dict[str, Any]:
        """Returns structured status of configured models and live OVMS instance."""
        try:
            cfg = load_json(self.config.config_json)
            current_name, current_path = extract_current_model(cfg)
        except Exception:
            current_name = self.config.model_name
            current_path = self.config.model_path

        ovms = probe_ovms_readiness(
            self.config.ovms_port,
            client_host=self.config.client_host,
            timeout_sec=1.5,
        )

        return {
            "configured_model": current_name,
            "configured_path": current_path,
            "ovms_port": self.config.ovms_port,
            "ovms_reachable": ovms.reachable,
            "ovms_models": ovms.models,
            "ovms_error": ovms.error,
        }

    def native_list(self, repository_path: Optional[str] = None) -> Dict[str, Any]:
        """Invokes native ovms.exe --list_models against model repository."""
        repo_dir = Path(repository_path).resolve() if repository_path else self.config.root / "models"
        ovms_exe = self.config.ovms_dir / "ovms.exe"
        if ovms_exe.exists():
            res = run_ovms_cli(self.config, ["--list_models", "--model_repository_path", str(repo_dir)])
            return {
                "native": True,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "repository_path": str(repo_dir),
            }
        else:
            return {
                "native": False,
                "message": "ovms.exe not available; listing local folders",
                "repository_path": str(repo_dir),
            }

    def switch_model(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        timeout_sec: int = 120,
        no_wait: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Atomically switches the single active model, updating config and triggering OVMS reload."""
        op_id = str(uuid.uuid4())
        registry = load_registry(self.config.legacy_registry_path) if self.config.legacy_registry_path.exists() else {}
        resolved_path = model_path or registry.get(model_name)

        if not resolved_path and model_name == self.config.model_name:
            resolved_path = self.config.model_path

        if not resolved_path:
            catalog = load_manifest(self.config.manifest_path) if self.config.manifest_path.exists() else {}
            entry = catalog.get(model_name)
            if entry and entry.default_name:
                resolved_path = str(self.config.root / "models" / entry.default_name)
            else:
                resolved_path = str(self.config.root / "models" / model_name)

        if not Path(resolved_path).exists():
            raise FileNotFoundError(f"Model path does not exist on disk: {resolved_path}")

        try:
            cfg = load_json(self.config.config_json)
            current_name, current_path = extract_current_model(cfg)
        except Exception:
            cfg = {}
            current_name = self.config.model_name
            current_path = self.config.model_path

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

        # Backup and write config atomically
        if self.config.config_json.exists():
            backup_config(self.config.config_json, self.config.backup_json)
        atomic_write_json(self.config.config_json, planned)

        # Update environment file
        if self.config.config_env.exists():
            update_env_file(
                self.config.config_env,
                {"MODEL_NAME": model_name, "MODEL_PATH": resolved_path},
            )

        # Update legacy registry for backward compatibility
        self._update_legacy_registry(model_name, resolved_path)

        # Check if OVMS is reachable
        ovms_check = probe_ovms_readiness(
            self.config.ovms_port,
            client_host=self.config.client_host,
            timeout_sec=1.0,
        )

        if not ovms_check.reachable or no_wait:
            return {
                "op_id": op_id,
                "changed": True,
                "state": "applied",
                "message": f"Config updated: '{model_name}' is set as active model (OVMS offline).",
                "model_name": model_name,
                "model_path": resolved_path,
            }

        # OVMS is online: Trigger live reload
        reload_config(self.config.ovms_port)

        # Wait for model readiness in OVMS memory
        ready = wait_for_ovms_ready(
            rest_port=self.config.ovms_port,
            client_host=self.config.client_host,
            timeout_sec=timeout_sec,
            expected_model=model_name,
        )

        if ready:
            return {
                "op_id": op_id,
                "changed": True,
                "state": "ready",
                "message": f"Successfully loaded and verified '{model_name}' in OVMS memory.",
                "model_name": model_name,
                "model_path": resolved_path,
            }

        # Timeout: Rollback safely
        rollback_config(self.config.backup_json, self.config.config_json)
        if self.config.config_env.exists():
            update_env_file(
                self.config.config_env,
                {"MODEL_NAME": current_name, "MODEL_PATH": current_path},
            )
        reload_config(self.config.ovms_port)
        raise TimeoutError(
            f"Model '{model_name}' was configured, but OVMS did not report it ready within {timeout_sec}s. Rolled back."
        )

    def configure_model(
        self,
        model_name: str,
        model_path: str,
        task: str = "text_generation",
        device: str = "GPU",
        performance_profile: str = "Balanced",
        config_path: Optional[str] = None,
        no_reload: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Executes native OVMS configure engine and updates local registry."""
        resolved_path = Path(model_path).resolve()
        if dry_run:
            return {
                "dry_run": True,
                "action": "configure",
                "model": model_name,
                "path": str(resolved_path),
                "task": task,
                "device": device,
            }

        if not resolved_path.exists():
            raise FileNotFoundError(f"Model path does not exist on disk: {resolved_path}")

        target_cfg_path = Path(config_path).resolve() if config_path else self.config.config_json
        ovms_exe = self.config.ovms_dir / "ovms.exe"

        native_configured = False
        if ovms_exe.exists():
            cache_size = 2 if performance_profile == "Safe" else (8 if performance_profile == "Fast" else 4)
            max_seqs = 2 if performance_profile == "Safe" else (8 if performance_profile == "Fast" else 4)
            args = [
                "--configure",
                "--model_path", str(resolved_path),
                "--model_name", model_name,
                "--task", task,
                "--target_device", device,
            ]
            if task == "text_generation":
                args.extend(["--cache_size", str(cache_size), "--max_num_seqs", str(max_seqs)])

            res = run_ovms_cli(self.config, args)
            if res.returncode == 0:
                native_configured = True

        # Ensure model is present in config.json
        try:
            current_cfg = load_json(target_cfg_path)
        except Exception:
            current_cfg = {}
        new_cfg = enable_model_in_config(current_cfg, model_name, str(resolved_path))
        if target_cfg_path.exists():
            backup_config(target_cfg_path, self.config.backup_json)
        atomic_write_json(target_cfg_path, new_cfg)
        self._update_legacy_registry(model_name, str(resolved_path))

        if not no_reload:
            ovms_check = probe_ovms_readiness(self.config.ovms_port, client_host=self.config.client_host, timeout_sec=1.0)
            if ovms_check.reachable:
                reload_config(self.config.ovms_port)

        return {
            "changed": True,
            "action": "configure",
            "model": model_name,
            "path": str(resolved_path),
            "native": native_configured,
            "message": f"Successfully configured model '{model_name}'.",
        }

    def enable_model(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        config_path: Optional[str] = None,
        task: str = "text_generation",
        device: str = "GPU",
        performance_profile: str = "Balanced",
        dry_run: bool = False,
        no_reload: bool = False,
    ) -> Dict[str, Any]:
        """Idempotently adds/enables a model in config.json while preserving all other models and unknown keys."""
        catalog = load_manifest(self.config.manifest_path) if self.config.manifest_path.exists() else {}
        entry = catalog.get(model_name)
        resolved_path = model_path
        if not resolved_path:
            legacy_reg = load_registry(self.config.legacy_registry_path) if self.config.legacy_registry_path.exists() else {}
            resolved_path = legacy_reg.get(model_name)
        if not resolved_path:
            resolved_path = str(self.config.root / "models" / model_name)

        if dry_run:
            return {"dry_run": True, "action": "enable", "model": model_name, "path": str(resolved_path)}

        target_cfg_path = Path(config_path).resolve() if config_path else self.config.config_json
        ovms_exe = self.config.ovms_dir / "ovms.exe"
        native_added = False

        if ovms_exe.exists() and Path(resolved_path).exists():
            res = run_ovms_cli(self.config, [
                "--add_to_config",
                "--config_path", str(target_cfg_path),
                "--model_name", model_name,
                "--model_path", str(resolved_path),
            ])
            if res.returncode == 0:
                native_added = True

        if not native_added:
            try:
                current_cfg = load_json(target_cfg_path)
            except Exception:
                current_cfg = {}
            new_cfg = enable_model_in_config(current_cfg, model_name, str(resolved_path))
            if target_cfg_path.exists():
                backup_config(target_cfg_path, self.config.backup_json)
            atomic_write_json(target_cfg_path, new_cfg)

        self._update_legacy_registry(model_name, str(resolved_path))

        if not no_reload:
            ovms_check = probe_ovms_readiness(
                self.config.ovms_port,
                client_host=self.config.client_host,
                timeout_sec=1.0,
            )
            if ovms_check.reachable:
                reload_config(self.config.ovms_port)

        return {
            "changed": True,
            "action": "enable",
            "model": model_name,
            "path": str(resolved_path),
            "native": native_added,
            "message": f"Enabled model '{model_name}' in config.",
        }

    def disable_model(
        self,
        model_name: str,
        config_path: Optional[str] = None,
        dry_run: bool = False,
        no_reload: bool = False,
    ) -> Dict[str, Any]:
        """Idempotently removes a model from config.json while preserving all other models."""
        if dry_run:
            return {"dry_run": True, "action": "disable", "model": model_name}

        target_cfg_path = Path(config_path).resolve() if config_path else self.config.config_json
        ovms_exe = self.config.ovms_dir / "ovms.exe"
        native_removed = False

        if ovms_exe.exists():
            res = run_ovms_cli(self.config, [
                "--remove_from_config",
                "--config_path", str(target_cfg_path),
                "--model_name", model_name,
            ])
            if res.returncode == 0:
                native_removed = True

        if not native_removed:
            try:
                current_cfg = load_json(target_cfg_path)
            except Exception:
                current_cfg = {}
            new_cfg = disable_model_in_config(current_cfg, model_name)
            if target_cfg_path.exists():
                backup_config(target_cfg_path, self.config.backup_json)
            atomic_write_json(target_cfg_path, new_cfg)

        if not no_reload:
            ovms_check = probe_ovms_readiness(
                self.config.ovms_port,
                client_host=self.config.client_host,
                timeout_sec=1.0,
            )
            if ovms_check.reachable:
                reload_config(self.config.ovms_port)

        return {
            "changed": True,
            "action": "disable",
            "model": model_name,
            "native": native_removed,
            "message": f"Disabled model '{model_name}' in config.",
        }

    def reload(self, timeout_sec: int = 30, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Triggers dynamic config reload on live OVMS instance."""
        ovms_check = probe_ovms_readiness(
            self.config.ovms_port,
            client_host=self.config.client_host,
            timeout_sec=1.0,
        )
        if not ovms_check.reachable:
            return {"reloaded": False, "message": "OVMS is offline; config changes apply on next launch."}

        ok = reload_config(self.config.ovms_port)
        return {"reloaded": ok, "message": "OVMS config reload accepted." if ok else "OVMS reload failed."}

    def rollback(self, target_backup: Optional[str] = None, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Restores last config.json and config.env backup."""
        backup_file = Path(target_backup).resolve() if target_backup else self.config.backup_json
        target_file = Path(config_path).resolve() if config_path else self.config.config_json

        if not backup_file.exists():
            raise FileNotFoundError(f"No backup found at {backup_file}")

        rollback_config(backup_file, target_file)
        cfg = load_json(target_file)
        name, model_path = extract_current_model(cfg)

        if self.config.config_env.exists() and name:
            update_env_file(self.config.config_env, {"MODEL_NAME": name, "MODEL_PATH": model_path})

        ovms_check = probe_ovms_readiness(
            self.config.ovms_port,
            client_host=self.config.client_host,
            timeout_sec=1.0,
        )
        if ovms_check.reachable:
            reload_config(self.config.ovms_port)

        return {"rolled_back_to": name, "model_path": model_path}

    def _update_legacy_registry(self, model_name: str, model_path: str) -> None:
        """Updates legacy artficats/models_registry.json for backward compatibility."""
        try:
            reg_path = self.config.legacy_registry_path
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            if reg_path.exists():
                registry = load_registry(reg_path)
            else:
                registry = {}
            registry[model_name] = model_path
            atomic_write_json(reg_path, {"models": registry})
        except Exception:
            pass
