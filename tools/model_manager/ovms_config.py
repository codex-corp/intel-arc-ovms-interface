from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple


class ConfigShapeError(ValueError):
    pass


@dataclass
class ConfigPaths:
    config_json: Path
    backup_json: Path


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"OVMS config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_current_model(data: Dict[str, Any]) -> Tuple[str, str]:
    model_list = data.get("model_config_list")
    if not isinstance(model_list, list) or not model_list:
        raise ConfigShapeError("config.json missing model_config_list[0]")

    first = model_list[0]
    cfg = first.get("config") if isinstance(first, dict) else None
    if not isinstance(cfg, dict):
        raise ConfigShapeError("config.json missing model_config_list[0].config")

    name = str(cfg.get("name", "")).strip()
    base_path = str(cfg.get("base_path", "")).strip()
    if not name or not base_path:
        raise ConfigShapeError("config.json missing model name/base_path")
    return name, base_path


def build_swapped_config(data: Dict[str, Any], model_name: str, model_path: str) -> Dict[str, Any]:
    model_list = data.get("model_config_list")
    if not isinstance(model_list, list) or not model_list:
        raise ConfigShapeError("config.json missing model_config_list[0]")
    first = model_list[0]
    if not isinstance(first, dict):
        raise ConfigShapeError("model_config_list[0] is invalid")
    cfg = first.get("config")
    if not isinstance(cfg, dict):
        raise ConfigShapeError("model_config_list[0].config is invalid")

    new_data = json.loads(json.dumps(data))
    new_cfg = new_data["model_config_list"][0]["config"]
    new_cfg["name"] = model_name
    new_cfg["base_path"] = model_path
    return new_data


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def backup_config(src: Path, dst: Path) -> None:
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def rollback_config(backup: Path, target: Path) -> None:
    if backup.exists():
        target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")

