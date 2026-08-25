from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.core.config import RuntimeConfig, load_core_config
from tools.core.config_engine import extract_current_model, load_json
from tools.core.lifecycle import OvmsLifecycleService
from tools.core.manifest import (
    discover_all_models,
    is_model_weights_ready,
    load_manifest,
)
from tools.core.process_manager import ProcessManager
from tools.core.readiness import (
    check_tcp_port,
    probe_gateway_readiness,
    probe_ovms_readiness,
)
from tools.model_manager.model_registry import load_registry

_tcp_probe = check_tcp_port

_GLOBAL_PROCESS_MANAGER: Optional[ProcessManager] = None
_GLOBAL_LIFECYCLE_SERVICE: Optional[OvmsLifecycleService] = None


def _get_process_manager(config: RuntimeConfig) -> ProcessManager:
    global _GLOBAL_PROCESS_MANAGER
    if _GLOBAL_PROCESS_MANAGER is None or _GLOBAL_PROCESS_MANAGER.config.root != config.root:
        _GLOBAL_PROCESS_MANAGER = ProcessManager(config)
    return _GLOBAL_PROCESS_MANAGER


def _get_lifecycle_service(config: RuntimeConfig) -> OvmsLifecycleService:
    global _GLOBAL_LIFECYCLE_SERVICE
    if _GLOBAL_LIFECYCLE_SERVICE is None or _GLOBAL_LIFECYCLE_SERVICE.config.root != config.root:
        _GLOBAL_LIFECYCLE_SERVICE = OvmsLifecycleService(config)
    return _GLOBAL_LIFECYCLE_SERVICE


@dataclass
class RuntimeStatus:
    ovms_reachable: bool
    gateway_reachable: bool
    loaded_models: List[str]
    configured_model: str
    registry_models: Dict[str, str]
    downloaded_models: List[str] = field(default_factory=list)
    enabled_models: List[str] = field(default_factory=list)
    ovms_error: Optional[str] = None


def is_model_downloaded(model_path_str: Optional[str]) -> bool:
    """Delegates model weight integrity verification to the Core manifest engine."""
    return is_model_weights_ready(model_path_str)


def get_downloaded_models(
    registry: Dict[str, str],
    configured_name: str = "",
    configured_path: str = "",
) -> List[str]:
    """Returns sorted list of all model names with complete weights present on disk."""
    downloaded: List[str] = []
    for name, path_str in registry.items():
        if is_model_weights_ready(path_str):
            downloaded.append(name)
    if configured_name and configured_name not in downloaded:
        if is_model_weights_ready(configured_path):
            downloaded.append(configured_name)
    return sorted(downloaded)


def read_enabled_models(config: RuntimeConfig) -> List[str]:
    """Reads configured active models from config.json without crashing on empty lists."""
    config_path = config.config_json
    if not config_path.exists():
        return [config.model_name] if config.model_name else []
    try:
        data = load_json(config_path)
        models = []
        for item in data.get("model_config_list", []):
            cfg = item.get("config", {}) if isinstance(item, dict) else {}
            n = cfg.get("name")
            if n:
                models.append(str(n).strip().lstrip("\ufeff"))
        return models
    except Exception:
        return [config.model_name] if config.model_name else []


def load_runtime_config(root: Optional[Path] = None) -> RuntimeConfig:
    """Loads centralized runtime configuration via Python Core."""
    return load_core_config(root)


def read_registry(config: RuntimeConfig) -> Dict[str, str]:
    """Reads legacy registry for backward compatibility."""
    if not config.legacy_registry_path.exists():
        return {}
    return load_registry(config.legacy_registry_path)


def get_runtime_status(config: RuntimeConfig) -> RuntimeStatus:
    """Collects system status using Core readiness and manifest discovery."""
    ovms_probe = probe_ovms_readiness(
        config.ovms_port,
        client_host=config.client_host,
        timeout_sec=1.5,
    )
    gateway_reachable = probe_gateway_readiness(
        config.proxy_port,
        client_host=config.client_host,
        timeout_sec=1.0,
    )
    registry = read_registry(config)
    discovered = discover_all_models(
        config,
        active_model=config.model_name,
        loaded_models=ovms_probe.models,
    )

    downloaded = [name for name, info in discovered.items() if info.is_downloaded]
    enabled = read_enabled_models(config)

    # Determine currently configured model from config.json
    try:
        cfg = load_json(config.config_json)
        current_name, _ = extract_current_model(cfg)
        configured_model = current_name or config.model_name
    except Exception:
        configured_model = config.model_name

    return RuntimeStatus(
        ovms_reachable=ovms_probe.reachable,
        gateway_reachable=gateway_reachable,
        loaded_models=ovms_probe.models,
        configured_model=configured_model,
        registry_models=registry,
        downloaded_models=sorted(downloaded),
        enabled_models=enabled,
        ovms_error=ovms_probe.error,
    )


def run_management_command(
    config: RuntimeConfig,
    command: str,
    model: Optional[str] = None,
    *,
    model_path: Optional[str] = None,
    timeout_sec: int = 60,
) -> subprocess.CompletedProcess[str]:
    """
    Executes model lifecycle commands directly via Python Core OvmsLifecycleService,
    returning CompletedProcess-compatible results with zero PowerShell subprocess overhead.
    """
    service = _get_lifecycle_service(config)

    try:
        if command == "switch":
            if not model:
                raise ValueError("Model name is required for switch.")
            res = service.switch_model(
                model_name=model,
                model_path=model_path,
                timeout_sec=timeout_sec,
            )
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", command, model],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        elif command == "enable":
            if not model:
                raise ValueError("Model name is required for enable.")
            res = service.enable_model(
                model_name=model,
                model_path=model_path,
            )
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", "enable", model],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        elif command == "disable":
            if not model:
                raise ValueError("Model name is required for disable.")
            res = service.disable_model(model)
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", "disable", model],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        elif command == "reload":
            res = service.reload()
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", "reload"],
                returncode=0 if res.get("reloaded", True) else 1,
                stdout=stdout,
                stderr="",
            )

        elif command == "rollback":
            res = service.rollback()
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", "rollback"],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        elif command == "status":
            res = service.status()
            stdout = json.dumps(res, indent=2)
            return subprocess.CompletedProcess(
                args=["python", "-m", "tools.core.lifecycle", "status"],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        else:
            raise ValueError(f"Unknown management command: {command}")

    except Exception as exc:
        return subprocess.CompletedProcess(
            args=["python", "-m", "tools.core.lifecycle", command, str(model or "")],
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def download_model_files(
    config: RuntimeConfig,
    model_name: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Download OpenVINO INT4 model weights using Core downloader (native pull with fallback)."""
    from tools.core.downloader import pull_model

    dest_dir = pull_model(config, model_name, on_progress=on_progress)
    return str(dest_dir)


def start_runtime_component(config: RuntimeConfig, component: str) -> subprocess.Popen:
    """Supervises OVMS or Gateway processes using Python Core ProcessManager with zero visible popups."""
    mgr = _get_process_manager(config)

    if component == "ovms":
        mgr.start_ovms(wait_for_ready=False)
        proc = mgr._owned_processes.get("ovms")
        if proc:
            return proc
    elif component == "gateway":
        mgr.start_gateway(wait_for_ready=False)
        proc = mgr._owned_processes.get("gateway")
        if proc:
            return proc
    else:
        raise ValueError(f"Unknown runtime component: {component}")

    # Fallback dummy process if already running externally
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        ["cmd.exe", "/c", "exit 0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def format_management_result(result: subprocess.CompletedProcess[str]) -> str:
    """Formats CompletedProcess output for display in TUI action output panel."""
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    parts = [part for part in (output, error) if part]
    if not parts:
        return f"Command exited with code {result.returncode}."
    return "\n".join(parts)
