from __future__ import annotations

import json
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
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_current_model(data: Dict[str, Any]) -> Tuple[str, str]:
    model_list = data.get("model_config_list")
    if not isinstance(model_list, list) or not model_list:
        return "", ""

    first = model_list[0]
    cfg = first.get("config") if isinstance(first, dict) else None
    if not isinstance(cfg, dict):
        return "", ""

    name = str(cfg.get("name", "")).strip().lstrip("\ufeff")
    base_path = str(cfg.get("base_path", "")).strip()
    return name, base_path


def build_swapped_config(data: Dict[str, Any], model_name: str, model_path: str) -> Dict[str, Any]:
    new_data = json.loads(json.dumps(data)) if data else {}
    model_list = new_data.get("model_config_list")

    if not isinstance(model_list, list) or not model_list:
        new_data["model_config_list"] = [
            {
                "config": {
                    "name": model_name,
                    "base_path": model_path,
                }
            }
        ]
        return new_data

    first = model_list[0]
    if not isinstance(first, dict) or "config" not in first or not isinstance(first["config"], dict):
        first = {"config": {}}

    new_cfg = first["config"]
    new_cfg["name"] = model_name
    new_cfg["base_path"] = model_path

    # Strictly ensure exactly 1 single active model entry in model_config_list (No duplicates!)
    new_data["model_config_list"] = [first]
    return new_data


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def backup_config(src: Path, dst: Path) -> None:
    dst.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")


def rollback_config(backup: Path, target: Path) -> None:
    if backup.exists():
        target.write_text(backup.read_text(encoding="utf-8-sig"), encoding="utf-8")
