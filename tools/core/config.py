from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class RuntimeConfig:
    """Centralized, immutable runtime configuration for all Core and TUI modules."""

    root: Path
    python_exe: Path
    ovms_port: int = 8000
    proxy_port: int = 8001
    proxy_bind_host: str = "127.0.0.1"
    default_model: str = "qwen2.5-coder-7b"
    model_name: str = "qwen2.5-coder-7b"
    model_path: str = ""
    ovms_dir: Optional[Path] = None
    ovms_grpc_port: int = 9000
    ovms_version: str = "2026.3"

    def __init__(
        self,
        root: Path,
        python_exe: Path,
        ovms_port: int = 8000,
        proxy_port: int = 8001,
        proxy_host: Optional[str] = None,
        proxy_bind_host: Optional[str] = None,
        default_model: str = "qwen2.5-coder-7b",
        model_name: str = "qwen2.5-coder-7b",
        model_path: str = "",
        ovms_dir: Optional[Path] = None,
        ovms_grpc_port: int = 9000,
        ovms_version: str = "2026.3",
    ):
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "python_exe", python_exe)
        object.__setattr__(self, "ovms_port", ovms_port)
        object.__setattr__(self, "proxy_port", proxy_port)
        bind_host = proxy_bind_host or proxy_host or "127.0.0.1"
        object.__setattr__(self, "proxy_bind_host", bind_host)
        object.__setattr__(self, "default_model", default_model)
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(self, "model_path", model_path)
        resolved_ovms_dir = ovms_dir or (root / "ovms" / "ovms_windows")
        object.__setattr__(self, "ovms_dir", resolved_ovms_dir)
        object.__setattr__(self, "ovms_grpc_port", ovms_grpc_port)
        object.__setattr__(self, "ovms_version", ovms_version)

    @property
    def proxy_host(self) -> str:
        """Alias for proxy_bind_host for backward compatibility."""
        return self.proxy_bind_host

    @property
    def client_host(self) -> str:
        """Normalized client address for outbound local connections, avoiding Windows 0.0.0.0 crashes."""
        if self.proxy_bind_host in {"0.0.0.0", "", "::", "localhost"}:
            return "127.0.0.1"
        return self.proxy_bind_host

    @property
    def bind_host(self) -> str:
        """The host interface to bind listening server sockets to."""
        return self.proxy_bind_host

    @property
    def gateway_base_url(self) -> str:
        return f"http://{self.client_host}:{self.proxy_port}/v3"

    @property
    def ovms_rest_url(self) -> str:
        return f"http://{self.client_host}:{self.ovms_port}"

    @property
    def config_json(self) -> Path:
        return self.root / "config.json"

    @property
    def backup_json(self) -> Path:
        return self.root / "config.json.bak"

    @property
    def config_env(self) -> Path:
        return self.root / "config.env"

    @property
    def manifest_path(self) -> Path:
        return self.root / "models_manifest.json"

    @property
    def legacy_registry_path(self) -> Path:
        return self.root / "artficats" / "models_registry.json"


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_core_config(root_override: Optional[Path] = None) -> RuntimeConfig:
    """Loads and merges runtime configuration from config.env, config.env.example, and system defaults."""
    if root_override:
        root = Path(root_override).resolve()
    else:
        root = Path(__file__).resolve().parents[2]

    env_values = _read_env_file(root / "config.env")
    example_values = _read_env_file(root / "config.env.example")

    def get(key: str, fallback: str) -> str:
        return (
            os.environ.get(key)
            or env_values.get(key)
            or example_values.get(key)
            or fallback
        )

    python_exe_raw = get("PYTHON_EXE", r".\.venv\Scripts\python.exe")
    python_exe = Path(python_exe_raw)
    if not python_exe.is_absolute():
        python_exe = (root / python_exe).resolve()

    ovms_dir_raw = get("OVMS_DIR", r"ovms\ovms_windows")
    ovms_dir = Path(ovms_dir_raw)
    if not ovms_dir.is_absolute():
        ovms_dir = (root / ovms_dir).resolve()

    default_model = get("DEFAULT_MODEL_NAME", get("MODEL_NAME", "qwen2.5-coder-7b"))
    model_name = get("MODEL_NAME", default_model)
    model_path = get("MODEL_PATH", "")

    return RuntimeConfig(
        root=root,
        python_exe=python_exe,
        ovms_dir=ovms_dir,
        ovms_port=int(get("OVMS_PORT", "8000")),
        ovms_grpc_port=int(get("OVMS_GRPC_PORT", "9000")),
        proxy_bind_host=get("PROXY_HOST", "127.0.0.1"),
        proxy_port=int(get("PROXY_PORT", "8001")),
        default_model=default_model,
        model_name=model_name,
        model_path=model_path,
        ovms_version=get("OVMS_VERSION", "2026.3"),
    )
