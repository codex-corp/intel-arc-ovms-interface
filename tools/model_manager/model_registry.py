from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

@dataclass(frozen=True)
class ModelRecord:
    name: str
    path: str
    source: str | None = None
    task: str = "text_generation"
    target_device: str = "GPU"
    profile: str = "balanced"

def load_registry(path: Path) -> Dict[str, ModelRecord]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: Dict[str, ModelRecord] = {}
    for name, value in data.get("models", {}).items():
        if isinstance(value, str):
            result[str(name)] = ModelRecord(name=str(name), path=value)
        elif isinstance(value, dict):
            result[str(name)] = ModelRecord(
                name=str(name), path=str(value.get("path", "")), source=value.get("source"),
                task=str(value.get("task", "text_generation")), target_device=str(value.get("target_device", "GPU")),
                profile=str(value.get("profile", "balanced")),
            )
    return result
