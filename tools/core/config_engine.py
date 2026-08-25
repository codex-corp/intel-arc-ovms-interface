from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    """Safely loads a JSON configuration file with UTF-8 BOM tolerance."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_current_model(data: Dict[str, Any]) -> Tuple[str, str]:
    """Extracts the active/first (name, base_path) tuple from model_config_list without failing on empty lists."""
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


def get_all_configured_models(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Returns a list of all configured model dictionaries ({'name': ..., 'base_path': ...})."""
    result: List[Dict[str, str]] = []
    model_list = data.get("model_config_list")
    if not isinstance(model_list, list):
        return result

    for item in model_list:
        if isinstance(item, dict) and isinstance(item.get("config"), dict):
            cfg = item["config"]
            name = str(cfg.get("name", "")).strip().lstrip("\ufeff")
            path = str(cfg.get("base_path", "")).strip()
            if name:
                result.append({"name": name, "base_path": path})
    return result


def enable_model_in_config(
    data: Dict[str, Any],
    model_name: str,
    model_path: str,
) -> Dict[str, Any]:
    """
    Adds or updates a model in model_config_list while:
    1. Preserving all other existing models in model_config_list.
    2. Preventing duplicate model names.
    3. Preserving all unknown top-level keys, plugin_config, and mediapipe_config_list.
    """
    new_data = json.loads(json.dumps(data)) if data else {}
    model_list = new_data.get("model_config_list")
    if not isinstance(model_list, list):
        model_list = []
        new_data["model_config_list"] = model_list

    # Update existing entry if present, or append new entry without creating duplicates
    found = False
    for item in model_list:
        if isinstance(item, dict) and isinstance(item.get("config"), dict):
            cfg = item["config"]
            if cfg.get("name") == model_name:
                cfg["base_path"] = model_path
                found = True
                break

    if not found:
        model_list.append({
            "config": {
                "name": model_name,
                "base_path": model_path,
            }
        })

    return new_data


def disable_model_in_config(data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Removes a specific model from model_config_list while:
    1. Preserving all other models in model_config_list.
    2. Preserving all unknown top-level keys, plugin_config, and mediapipe_config_list.
    """
    new_data = json.loads(json.dumps(data)) if data else {}
    model_list = new_data.get("model_config_list")
    if not isinstance(model_list, list):
        return new_data

    new_list = [
        item for item in model_list
        if not (isinstance(item, dict) and isinstance(item.get("config"), dict) and item["config"].get("name") == model_name)
    ]
    new_data["model_config_list"] = new_list
    return new_data


def build_swapped_config(data: Dict[str, Any], model_name: str, model_path: str) -> Dict[str, Any]:
    """
    Updates the active model for single-model swap while:
    1. Preserving unknown top-level keys.
    2. Preserving plugin_config and device parameters.
    3. Preserving mediapipe_config_list.
    4. Preventing duplicate model entries.
    """
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

    new_data["model_config_list"] = [first]
    return new_data


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Writes JSON payload atomically using a temporary file to prevent corruption."""
    temp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def backup_config(src: Path, dst: Path) -> None:
    """Creates a backup copy of a configuration file."""
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")


def rollback_config(backup: Path, target: Path) -> None:
    """Restores a configuration file from backup."""
    if backup.exists():
        target.write_text(backup.read_text(encoding="utf-8-sig"), encoding="utf-8")
