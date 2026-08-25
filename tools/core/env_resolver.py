from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

_CACHED_OVMS_ENV: Optional[Dict[str, str]] = None


def resolve_ovms_environment(ovms_dir: Path, force_refresh: bool = False) -> Dict[str, str]:
    """
    Executes Windows setupvars.bat once in a hidden, non-interactive cmd process,
    captures the resulting environment variables, and caches them in Python memory.
    """
    global _CACHED_OVMS_ENV

    if _CACHED_OVMS_ENV is not None and not force_refresh:
        return _CACHED_OVMS_ENV.copy()

    setupvars_bat = ovms_dir / "setupvars.bat"
    if not setupvars_bat.exists() or os.name != "nt":
        # Fallback to current process environment if not on Windows or setupvars missing
        env = os.environ.copy()
        _CACHED_OVMS_ENV = env
        return env.copy()

    cmd_line = f'call "{setupvars_bat}" && set'
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            cmd_line,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(ovms_dir),
            creationflags=creationflags,
            timeout=15,
        )
        if proc.returncode != 0:
            env = os.environ.copy()
            _CACHED_OVMS_ENV = env
            return env.copy()

        extracted_env: Dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                extracted_env[key] = val

        # Merge extracted setupvars on top of base environment
        merged = os.environ.copy()
        merged.update(extracted_env)
        _CACHED_OVMS_ENV = merged
        return merged.copy()

    except Exception:
        env = os.environ.copy()
        _CACHED_OVMS_ENV = env
        return env.copy()


def clear_environment_cache() -> None:
    """Clears the in-memory environment cache for testing or re-initialization."""
    global _CACHED_OVMS_ENV
    _CACHED_OVMS_ENV = None
