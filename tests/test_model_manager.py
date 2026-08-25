import json
import tempfile
import unittest
from pathlib import Path

from tools.model_manager.model_registry import load_registry
from tools.model_manager.ovms_config import (
    ConfigShapeError,
    atomic_write_json,
    backup_config,
    build_swapped_config,
    extract_current_model,
    load_json,
    rollback_config,
)


class ModelManagerTests(unittest.TestCase):
    def test_registry_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models_registry.json"
            self.assertEqual({}, load_registry(path))

    def test_registry_loads_models_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models_registry.json"
            path.write_text(json.dumps({"models": {"qwen": ".\\models\\qwen"}}), encoding="utf-8")
            self.assertEqual({"qwen": ".\\models\\qwen"}, load_registry(path))

    def test_registry_handles_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models_registry.json"
            path.write_text("\ufeff" + json.dumps({"models": {"qwen": ".\\models\\qwen"}}), encoding="utf-8")
            self.assertEqual({"qwen": ".\\models\\qwen"}, load_registry(path))

    def test_extract_and_swap_preserve_extra_config(self):
        config = {
            "model_config_list": [
                {
                    "config": {
                        "name": "old",
                        "base_path": "old-path",
                        "target_device": "GPU",
                        "plugin_config": {"KV_CACHE_PRECISION": "u8"},
                    }
                }
            ],
            "global_setting": True,
        }

        self.assertEqual(("old", "old-path"), extract_current_model(config))
        swapped = build_swapped_config(config, "new", "new-path")

        self.assertEqual(("new", "new-path"), extract_current_model(swapped))
        self.assertEqual("GPU", swapped["model_config_list"][0]["config"]["target_device"])
        self.assertEqual(
            {"KV_CACHE_PRECISION": "u8"},
            swapped["model_config_list"][0]["config"]["plugin_config"],
        )
        self.assertTrue(swapped["global_setting"])
        self.assertEqual(("old", "old-path"), extract_current_model(config))

    def test_empty_config_graceful_handling(self):
        self.assertEqual(("", ""), extract_current_model({}))
        swapped = build_swapped_config({"model_config_list": []}, "x", "y")
        self.assertEqual(("x", "y"), extract_current_model(swapped))
        self.assertEqual(1, len(swapped["model_config_list"]))

    def test_atomic_write_backup_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            backup_path = root / "config.json.bak"
            original = {
                "model_config_list": [{"config": {"name": "old", "base_path": "old-path"}}]
            }
            replacement = {
                "model_config_list": [{"config": {"name": "new", "base_path": "new-path"}}]
            }

            atomic_write_json(config_path, original)
            backup_config(config_path, backup_path)
            atomic_write_json(config_path, replacement)
            rollback_config(backup_path, config_path)

            self.assertEqual(original, load_json(config_path))
            self.assertFalse((root / "config.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
