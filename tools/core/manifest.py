from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from tools.core.config import RuntimeConfig
from tools.model_manager.model_registry import load_registry


@dataclass(frozen=True)
class ModelCatalogEntry:
    """Portable, machine-independent metadata for a verified OpenVINO model."""

    name: str
    repo_id: str
    default_name: str
    task: str = "text_generation"
    device: str = "GPU"
    precision: str = "int4"
    description: str = ""
    default_profile: str = "Balanced"


@dataclass
class ModelStatusInfo:
    """Unified runtime state for a model, combining catalog metadata and local disk state."""

    name: str
    repo_id: Optional[str]
    local_path: Optional[str]
    is_downloaded: bool
    is_active: bool
    is_loaded: bool
    description: str = ""
    catalog_entry: Optional[ModelCatalogEntry] = None


def load_manifest(manifest_path: Path) -> Dict[str, ModelCatalogEntry]:
    """Loads and validates the portable model catalog from models_manifest.json."""
    if not manifest_path.exists():
        return {}

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}

    raw_models = data.get("models", {})
    catalog: Dict[str, ModelCatalogEntry] = {}

    for raw_name, meta in raw_models.items():
        if not isinstance(meta, dict):
            continue
        clean_name = str(raw_name).strip().lstrip("\ufeff")
        repo_id = str(meta.get("repo_id", "")).strip()
        if not repo_id:
            # Strictly ignore entries without verified repo_id
            continue

        catalog[clean_name] = ModelCatalogEntry(
            name=clean_name,
            repo_id=repo_id,
            default_name=str(meta.get("default_name", clean_name)).strip(),
            task=str(meta.get("task", "text_generation")).strip(),
            device=str(meta.get("device", "GPU")).strip(),
            precision=str(meta.get("precision", "int4")).strip(),
            description=str(meta.get("description", "")).strip(),
            default_profile=str(meta.get("default_profile", "Balanced")).strip(),
        )

    return catalog


def is_model_weights_ready(path_str: Optional[str]) -> bool:
    """Strictly verifies that binary model weights and required XML/GGUF definitions exist on disk."""
    if not path_str:
        return False
    try:
        p = Path(path_str)
        if not p.exists() or not p.is_dir():
            return False

        has_xml = (p / "openvino_model.xml").exists()
        has_bin = (
            (p / "openvino_model.bin").exists()
            or any(p.glob("openvino_model*.bin"))
            or any(p.glob("*.gguf"))
        )
        return (has_xml and has_bin) or any(p.glob("*.gguf"))
    except Exception:
        return False


def discover_all_models(
    config: RuntimeConfig,
    active_model: str = "",
    loaded_models: Optional[List[str]] = None,
) -> Dict[str, ModelStatusInfo]:
    """
    Aggregates models across the portable manifest, local registry, and live runtime state.
    Local models without verified upstream repos are marked as discovered local models (repo_id=None).
    """
    catalog = load_manifest(config.manifest_path)
    legacy_registry = load_registry(config.legacy_registry_path) if config.legacy_registry_path.exists() else {}
    loaded_set = set(loaded_models or [])

    all_names = set(catalog.keys()) | set(legacy_registry.keys())
    if active_model:
        all_names.add(active_model)
    all_names.update(loaded_set)

    discovered: Dict[str, ModelStatusInfo] = {}

    for name in sorted(all_names):
        catalog_entry = catalog.get(name)
        repo_id = catalog_entry.repo_id if catalog_entry else None
        local_path = legacy_registry.get(name)

        if not local_path and name == config.model_name and config.model_path:
            local_path = config.model_path

        is_downloaded = is_model_weights_ready(local_path)
        is_active = (name == active_model)
        is_loaded = (name in loaded_set)
        desc = catalog_entry.description if catalog_entry else "Local custom model"

        discovered[name] = ModelStatusInfo(
            name=name,
            repo_id=repo_id,
            local_path=local_path,
            is_downloaded=is_downloaded,
            is_active=is_active,
            is_loaded=is_loaded,
            description=desc,
            catalog_entry=catalog_entry,
        )

    return discovered
