from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class RuntimeSettings:
    ovms_dir: Path
    model_repository: Path
    config_path: Path

def load_runtime_settings(root: Path) -> RuntimeSettings:
    data = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    return RuntimeSettings(
        ovms_dir=(root / data["paths"]["ovms_dir"]).resolve(),
        model_repository=(root / data["paths"]["model_repository"]).resolve(),
        config_path=(root / "config.json").resolve(),
    )

def run_ovms_cli(root: Path, args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cfg = load_runtime_settings(root)
    exe = cfg.ovms_dir / "ovms.exe"
    setup = cfg.ovms_dir / "setupvars.bat"
    if not exe.exists():
        raise FileNotFoundError(f"ovms.exe not found: {exe}")
    arg_line = subprocess.list2cmdline([str(exe), *list(args)])
    command = arg_line if not setup.exists() else f'call "{setup}" >NUL 2>&1 && {arg_line}'
    return subprocess.run(["cmd.exe", "/d", "/s", "/c", command], cwd=cfg.ovms_dir, text=True, capture_output=True, check=check)
