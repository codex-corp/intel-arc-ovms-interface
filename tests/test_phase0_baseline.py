from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.model_manager.model_registry import load_registry
from tools.model_manager.ovms_client import fetch_models
from tools.model_manager.ovms_config import (
    atomic_write_json,
    backup_config,
    build_swapped_config,
    extract_current_model,
    load_json,
    rollback_config,
)
from tools.tui.backend import (
    RuntimeConfig,
    get_downloaded_models,
    is_model_downloaded,
    load_runtime_config,
    read_enabled_models,
)


class Phase0BaselineCompatibilityContractTests(unittest.TestCase):
    """
    Phase 0 Contract: Freezes and verifies all baseline runtime, config,
    registry, network, and model validity rules that the Python Core must preserve.
    """

    def test_config_preserves_unknown_keys_and_plugins(self):
        """Preserves custom top-level keys, plugin_config, and mediapipe structures."""
        original = {
            "model_config_list": [
                {
                    "config": {
                        "name": "model-a",
                        "base_path": "path-a",
                        "target_device": "GPU",
                        "plugin_config": {"KV_CACHE_PRECISION": "u8", "NUM_STREAMS": "1"},
                    }
                }
            ],
            "mediapipe_config_list": [
                {"name": "pipe-1", "base_path": "pipe-path"}
            ],
            "custom_metadata": {"author": "Intel Arc Team", "version": "2026.3"},
            "global_setting": True,
        }

        swapped = build_swapped_config(original, "model-b", "path-b")

        # Active model is updated
        self.assertEqual(("model-b", "path-b"), extract_current_model(swapped))
        # Plugin config and target device are preserved
        self.assertEqual("GPU", swapped["model_config_list"][0]["config"]["target_device"])
        self.assertEqual(
            {"KV_CACHE_PRECISION": "u8", "NUM_STREAMS": "1"},
            swapped["model_config_list"][0]["config"]["plugin_config"],
        )
        # Custom keys and mediapipe list are preserved
        self.assertEqual(1, len(swapped["mediapipe_config_list"]))
        self.assertEqual("pipe-1", swapped["mediapipe_config_list"][0]["name"])
        self.assertEqual({"author": "Intel Arc Team", "version": "2026.3"}, swapped["custom_metadata"])
        self.assertTrue(swapped["global_setting"])
        # Exactly 1 active model entry (no duplicate models)
        self.assertEqual(1, len(swapped["model_config_list"]))

    def test_config_atomic_write_and_rollback_integrity(self):
        """Validates atomic write and rollback mechanisms."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "config.json"
            bak_path = root / "config.json.bak"

            initial = {"model_config_list": [{"config": {"name": "initial", "base_path": "p1"}}]}
            modified = {"model_config_list": [{"config": {"name": "modified", "base_path": "p2"}}]}

            atomic_write_json(cfg_path, initial)
            backup_config(cfg_path, bak_path)
            self.assertEqual(initial, load_json(bak_path))

            atomic_write_json(cfg_path, modified)
            self.assertEqual(modified, load_json(cfg_path))

            rollback_config(bak_path, cfg_path)
            self.assertEqual(initial, load_json(cfg_path))
            self.assertFalse((root / "config.json.tmp").exists())

    def test_registry_handles_utf8_bom_and_normalizes_names(self):
        """Verifies UTF-8 BOM tolerance and key sanitization."""
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "models_registry.json"
            raw_content = "\ufeff" + json.dumps({
                "models": {
                    "  \ufeffQwen3-1.7B  ": "  g:\\models\\qwen3-1.7b  ",
                    "qwen2.5-coder-7b": "g:\\models\\qwen2.5",
                }
            })
            reg_path.write_text(raw_content, encoding="utf-8")

            registry = load_registry(reg_path)
            self.assertIn("Qwen3-1.7B", registry)
            self.assertEqual("g:\\models\\qwen3-1.7b", registry["Qwen3-1.7B"])
            self.assertIn("qwen2.5-coder-7b", registry)

    def test_model_weight_verification_requires_xml_and_bin(self):
        """Requires both .xml and .bin weights (or .gguf), rejecting incomplete metadata-only dirs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_ov = root / "valid_ov"
            valid_ov.mkdir()
            (valid_ov / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (valid_ov / "openvino_model.bin").write_bytes(b"\x00" * 128)

            metadata_only = root / "metadata_only"
            metadata_only.mkdir()
            (metadata_only / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (metadata_only / "tokenizer.json").write_text("{}", encoding="utf-8")

            valid_gguf = root / "valid_gguf"
            valid_gguf.mkdir()
            (valid_gguf / "model.gguf").write_bytes(b"GGUF" + b"\x00" * 32)

            self.assertTrue(is_model_downloaded(str(valid_ov)))
            self.assertFalse(is_model_downloaded(str(metadata_only)))
            self.assertTrue(is_model_downloaded(str(valid_gguf)))
            self.assertFalse(is_model_downloaded(str(root / "nonexistent")))

    def test_runtime_config_normalizes_client_addresses(self):
        """Binds to configured host but normalizes local client connection host to 127.0.0.1."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.env").write_text(
                "OVMS_PORT=8000\nPROXY_PORT=8001\nPROXY_HOST=0.0.0.0\nMODEL_NAME=test-model\n",
                encoding="utf-8",
            )
            config = load_runtime_config(root)
            self.assertEqual("0.0.0.0", config.proxy_host)
            self.assertEqual("127.0.0.1", config.client_host)
            self.assertEqual("http://127.0.0.1:8001/v3", config.gateway_base_url)

    def test_read_enabled_models_handles_empty_and_populated_configs(self):
        """Extracts configured models safely regardless of list size."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_port=8000,
                proxy_port=8001,
                proxy_host="127.0.0.1",
                default_model="default",
                model_name="default",
                model_path="",
            )

            # Missing config.json falls back to default model
            self.assertEqual(["default"], read_enabled_models(config))

            # Empty model_config_list
            (root / "config.json").write_text(json.dumps({"model_config_list": []}), encoding="utf-8")
            self.assertEqual([], read_enabled_models(config))

            # Populated list
            (root / "config.json").write_text(
                json.dumps({
                    "model_config_list": [
                        {"config": {"name": "Qwen3-1.7B", "base_path": "path1"}},
                        {"config": {"name": "qwen2.5-coder-7b", "base_path": "path2"}},
                    ]
                }),
                encoding="utf-8",
            )
            self.assertEqual(["Qwen3-1.7B", "qwen2.5-coder-7b"], read_enabled_models(config))

    def test_ovms_client_offline_graceful_handling(self):
        """Unreachable OVMS server returns clean OvmsStatus without raising uncaught exceptions."""
        status = fetch_models(rest_port=59999, timeout_sec=1)
        self.assertFalse(status.reachable)
        self.assertEqual([], status.models)
        self.assertIsNone(status.raw)
        self.assertIsNotNone(status.error)


if __name__ == "__main__":
    unittest.main()
