from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from tools.model_manager.model_registry import load_registry
from tools.model_manager.ovms_client import fetch_models


@dataclass
class RuntimeConfig:
    root: Path
    python_exe: Path
    ovms_port: int
    proxy_port: int
    proxy_host: str
    default_model: str
    model_name: str
    model_path: str

    @property
    def gateway_base_url(self) -> str:
        return f"http://{self.proxy_host}:{self.proxy_port}/v3"


@dataclass
class RuntimeStatus:
    ovms_reachable: bool
    gateway_reachable: bool
    loaded_models: List[str]
    configured_model: str
    registry_models: Dict[str, str]
    ovms_error: Optional[str] = None


def _load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_runtime_config(root: Path | None = None) -> RuntimeConfig:
    root = (root or Path(__file__).resolve().parents[2]).resolve()
    values = _load_env_file(root / "config.env")
    example = _load_env_file(root / "config.env.example")

    def get(key: str, fallback: str) -> str:
        return values.get(key) or example.get(key) or fallback

    python_exe = Path(get("PYTHON_EXE", r".\.venv\Scripts\python.exe"))
    if not python_exe.is_absolute():
        python_exe = (root / python_exe).resolve()

    return RuntimeConfig(
        root=root,
        python_exe=python_exe,
        ovms_port=int(get("OVMS_PORT", "8000")),
        proxy_port=int(get("PROXY_PORT", "8001")),
        proxy_host=get("PROXY_HOST", "127.0.0.1"),
        default_model=get("DEFAULT_MODEL_NAME", get("MODEL_NAME", "")),
        model_name=get("MODEL_NAME", ""),
        model_path=get("MODEL_PATH", ""),
    )


def read_registry(config: RuntimeConfig) -> Dict[str, str]:
    return load_registry(config.root / "artficats" / "models_registry.json")


def get_runtime_status(config: RuntimeConfig) -> RuntimeStatus:
    ovms = fetch_models(config.ovms_port, timeout_sec=2)
    gateway_reachable = _tcp_probe(config.proxy_host, config.proxy_port)
    return RuntimeStatus(
        ovms_reachable=ovms.reachable,
        gateway_reachable=gateway_reachable,
        loaded_models=ovms.models,
        configured_model=config.model_name,
        registry_models=read_registry(config),
        ovms_error=ovms.error,
    )


def _tcp_probe(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def _powershell_args(script: Path, *arguments: str) -> List[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments,
    ]


def run_management_command(
    config: RuntimeConfig,
    command: str,
    model: str | None = None,
    *,
    model_path: str | None = None,
    timeout_sec: int = 180,
) -> subprocess.CompletedProcess[str]:
    """Call the existing stable management surface without duplicating lifecycle logic."""
    script = config.root / "manage_models.ps1"
    arguments = [command]
    if model:
        arguments.append(model)
    if model_path:
        arguments.extend(["-Path", model_path])

    return subprocess.run(
        _powershell_args(script, *arguments),
        cwd=config.root,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=os.environ.copy(),
    )


def start_runtime_component(config: RuntimeConfig, component: str) -> subprocess.Popen:
    """Start OVMS or the compatibility gateway as a hidden child process on Windows."""
    scripts = {
        "ovms": config.root / "start_server_dynamic.ps1",
        "gateway": config.root / "run_ide_proxy.ps1",
    }
    if component not in scripts:
        raise ValueError(f"Unknown runtime component: {component}")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        _powershell_args(scripts[component]),
        cwd=config.root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=os.environ.copy(),
        creationflags=creationflags,
    )


def format_management_result(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    parts = [part for part in (output, error) if part]
    if not parts:
        return f"Command exited with code {result.returncode}."
    return "\n".join(parts)
