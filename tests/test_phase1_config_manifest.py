from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.core.config import RuntimeConfig, load_core_config
from tools.core.manifest import (
    ModelCatalogEntry,
    discover_all_models,
    is_model_weights_ready,
    load_manifest,
)


class Phase1ConfigAndManifestTests(unittest.TestCase):
    """Unit tests for Phase 1: Centralized Runtime Config & Portable Model Manifest."""

    def test_load_core_config_prefers_config_env_and_normalizes_client_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.env.example").write_text(
                "OVMS_PORT=8000\nPROXY_PORT=8001\nPROXY_HOST=0.0.0.0\nMODEL_NAME=default-model\n",
                encoding="utf-8",
            )
            (root / "config.env").write_text(
                "OVMS_PORT=9000\nPROXY_PORT=9001\nPROXY_HOST=0.0.0.0\nMODEL_NAME=custom-model\n",
                encoding="utf-8",
            )

            cfg = load_core_config(root)

            self.assertEqual(root.resolve(), cfg.root.resolve())
            self.assertEqual(9000, cfg.ovms_port)
            self.assertEqual(9001, cfg.proxy_port)
            self.assertEqual("0.0.0.0", cfg.bind_host)
            self.assertEqual("127.0.0.1", cfg.client_host)
            self.assertEqual("http://127.0.0.1:9001/v3", cfg.gateway_base_url)
            self.assertEqual("http://127.0.0.1:9000", cfg.ovms_rest_url)
            self.assertEqual("custom-model", cfg.model_name)

    def test_load_manifest_validates_and_filters_unverified_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = Path(tmp) / "models_manifest.json"
            data = {
                "version": "1.0",
                "models": {
                    "Qwen3-1.7B": {
                        "repo_id": "OpenVINO/Qwen3-1.7B-int4-ov",
                        "default_name": "qwen3-1.7b",
                        "description": "Lightweight model",
                    },
                    "Invalid-Model-No-Repo": {
                        "repo_id": "",
                        "description": "Missing repo",
                    },
                },
            }
            manifest_file.write_text(json.dumps(data), encoding="utf-8")

            catalog = load_manifest(manifest_file)
            self.assertIn("Qwen3-1.7B", catalog)
            self.assertEqual("OpenVINO/Qwen3-1.7B-int4-ov", catalog["Qwen3-1.7B"].repo_id)
            self.assertEqual("Lightweight model", catalog["Qwen3-1.7B"].description)
            self.assertNotIn("Invalid-Model-No-Repo", catalog)

    def test_is_model_weights_ready_strict_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_ov = root / "valid_ov"
            valid_ov.mkdir()
            (valid_ov / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (valid_ov / "openvino_model.bin").write_bytes(b"\x00" * 64)

            metadata_only = root / "metadata_only"
            metadata_only.mkdir()
            (metadata_only / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")

            valid_gguf = root / "valid_gguf"
            valid_gguf.mkdir()
            (valid_gguf / "model.gguf").write_bytes(b"GGUF")

            self.assertTrue(is_model_weights_ready(str(valid_ov)))
            self.assertFalse(is_model_weights_ready(str(metadata_only)))
            self.assertTrue(is_model_weights_ready(str(valid_gguf)))
            self.assertFalse(is_model_weights_ready(None))

    def test_discover_all_models_merges_catalog_registry_and_local_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "models_manifest.json"
            registry_path = root / "artficats" / "models_registry.json"
            registry_path.parent.mkdir(parents=True)

            # 1. Manifest with verified repo
            manifest_data = {
                "version": "1.0",
                "models": {
                    "Qwen3-1.7B": {
                        "repo_id": "OpenVINO/Qwen3-1.7B-int4-ov",
                        "default_name": "qwen3-1.7b",
                    }
                },
            }
            manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

            # 2. Local model on disk
            model_dir = root / "local_qwen"
            model_dir.mkdir()
            (model_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (model_dir / "openvino_model.bin").write_bytes(b"\x00" * 32)

            # 3. Uncataloged custom local model in registry
            registry_data = {
                "models": {
                    "Qwen3-1.7B": str(model_dir),
                    "My-Custom-Local-Model": str(root / "custom_path"),
                }
            }
            registry_path.write_text(json.dumps(registry_data), encoding="utf-8")

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=8000,
                ovms_grpc_port=9000,
                proxy_bind_host="127.0.0.1",
                proxy_port=8001,
                default_model="Qwen3-1.7B",
                model_name="Qwen3-1.7B",
                model_path=str(model_dir),
                ovms_version="2026.3",
            )

            discovered = discover_all_models(cfg, active_model="Qwen3-1.7B", loaded_models=["Qwen3-1.7B"])

            # Verified catalog model
            self.assertIn("Qwen3-1.7B", discovered)
            self.assertEqual("OpenVINO/Qwen3-1.7B-int4-ov", discovered["Qwen3-1.7B"].repo_id)
            self.assertTrue(discovered["Qwen3-1.7B"].is_downloaded)
            self.assertTrue(discovered["Qwen3-1.7B"].is_active)
            self.assertTrue(discovered["Qwen3-1.7B"].is_loaded)

            # Custom local model without verified upstream repo
            self.assertIn("My-Custom-Local-Model", discovered)
            self.assertIsNone(discovered["My-Custom-Local-Model"].repo_id)
            self.assertFalse(discovered["My-Custom-Local-Model"].is_downloaded)


if __name__ == "__main__":
    unittest.main()
