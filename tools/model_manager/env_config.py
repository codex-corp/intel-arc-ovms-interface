from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class EnvConfig:
    values: Dict[str, str]
    lines: List[str]


def load_env_file(path: Path) -> EnvConfig:
    values: Dict[str, str] = {}
    lines: List[str] = []
    if not path.exists():
        return EnvConfig(values=values, lines=lines)

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return EnvConfig(values=values, lines=lines)


def update_env_file(path: Path, updates: Dict[str, str]) -> None:
    cfg = load_env_file(path)
    out: List[str] = []
    seen = set()

    for line in cfg.lines:
        if "=" not in line or line.strip().startswith("#"):
            out.append(line)
            continue
        key, _ = line.split("=", 1)
        k = key.strip()
        if k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)

    for k, v in updates.items():
        if k not in seen and k not in cfg.values:
            out.append(f"{k}={v}")

    temp = path.with_suffix(path.suffix + ".tmp")
    text = "\n".join(out) + "\n"
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def required_value(values: Dict[str, str], key: str, default: str | None = None) -> str:
    if key in values and values[key]:
        return values[key]
    if default is not None:
        return default
    raise ValueError(f"Missing required config value: {key}")

