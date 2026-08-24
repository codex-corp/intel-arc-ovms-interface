from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Tuple
class ConfigShapeError(ValueError): pass

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists(): raise FileNotFoundError(f"OVMS config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))

def _model_list(data: Dict[str, Any]) -> list:
    models = data.setdefault("model_config_list", [])
    if not isinstance(models, list): raise ConfigShapeError("config.json model_config_list must be a list")
    return models

def extract_current_model(data: Dict[str, Any]) -> Tuple[str, str]:
    models = _model_list(data)
    if not models: raise ConfigShapeError("config.json has no configured models")
    cfg = models[0].get("config", {}) if isinstance(models[0], dict) else {}
    name, path = str(cfg.get("name", "")).strip(), str(cfg.get("base_path", "")).strip()
    if not name or not path: raise ConfigShapeError("configured model missing name/base_path")
    return name, path

def build_swapped_config(data: Dict[str, Any], model_name: str, model_path: str) -> Dict[str, Any]:
    new_data = json.loads(json.dumps(data)); models = _model_list(new_data); entry = {"config": {"name": model_name, "base_path": model_path}}
    if models: models[0] = entry
    else: models.append(entry)
    return new_data

def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp"); temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8"); temp.replace(path)
def backup_config(src: Path, dst: Path) -> None:
    if src.exists(): dst.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")
def rollback_config(backup: Path, target: Path) -> None:
    if backup.exists(): target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
