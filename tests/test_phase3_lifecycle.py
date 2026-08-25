from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.core.config import RuntimeConfig
from tools.core.lifecycle import OvmsLifecycleService


class Phase3LifecycleServiceTests(unittest.TestCase):
    """Unit tests for Phase 3: Native OVMS Lifecycle Service."""

    def test_switch_model_updates_config_and_env_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "models" / "test-model"
            model_dir.mkdir(parents=True)
            (model_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (model_dir / "openvino_model.bin").write_bytes(b"\x00" * 32)

            (root / "config.env").write_text("MODEL_NAME=initial\nMODEL_PATH=p1\n", encoding="utf-8")
            initial_json = {
                "model_config_list": [{"config": {"name": "initial", "base_path": "p1"}}],
                "custom_engine_param": "intel_arc",
            }
            (root / "config.json").write_text(json.dumps(initial_json), encoding="utf-8")

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=59000,
                ovms_grpc_port=59001,
                proxy_bind_host="127.0.0.1",
                proxy_port=59002,
                default_model="initial",
                model_name="initial",
                model_path="p1",
                ovms_version="2026.3",
            )

            service = OvmsLifecycleService(cfg)
            res = service.switch_model("test-model", model_path=str(model_dir))

            self.assertTrue(res["changed"])
            self.assertEqual("applied", res["state"])
            self.assertEqual("test-model", res["model_name"])

            # Verify config.json
            updated_json = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(updated_json["model_config_list"]))
            self.assertEqual("test-model", updated_json["model_config_list"][0]["config"]["name"])
            self.assertEqual(str(model_dir), updated_json["model_config_list"][0]["config"]["base_path"])
            self.assertEqual("intel_arc", updated_json["custom_engine_param"])  # Preserved!

            # Verify config.env
            env_text = (root / "config.env").read_text(encoding="utf-8")
            self.assertIn("MODEL_NAME=test-model", env_text)
            self.assertIn(f"MODEL_PATH={str(model_dir)}", env_text)

    def test_switch_model_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "models" / "target"
            model_dir.mkdir(parents=True)

            (root / "config.json").write_text(
                json.dumps({"model_config_list": [{"config": {"name": "current", "base_path": "p0"}}]}),
                encoding="utf-8",
            )
            (root / "config.env").write_text("MODEL_NAME=current\nMODEL_PATH=p0\n", encoding="utf-8")

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=59000,
                ovms_grpc_port=59001,
                proxy_bind_host="127.0.0.1",
                proxy_port=59002,
                default_model="current",
                model_name="current",
                model_path="p0",
                ovms_version="2026.3",
            )

            service = OvmsLifecycleService(cfg)
            res = service.switch_model("target", model_path=str(model_dir), dry_run=True)

            self.assertFalse(res["changed"])
            self.assertTrue(res["dry_run"])
            self.assertEqual("current", res["from_model"])
            self.assertEqual("target", res["to_model"])

            # Files unchanged
            current_cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual("current", current_cfg["model_config_list"][0]["config"]["name"])

    def test_enable_and_disable_model_preserves_other_models_and_mediapipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial_data = {
                "model_config_list": [
                    {"config": {"name": "model-a", "base_path": "/path/a"}},
                    {"config": {"name": "model-b", "base_path": "/path/b"}},
                ],
                "mediapipe_config_list": [{"name": "pipeline-1"}],
                "custom_key": "arc-gpu",
            }
            (root / "config.json").write_text(
                json.dumps(initial_data),
                encoding="utf-8",
            )

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=59000,
                ovms_grpc_port=59001,
                proxy_bind_host="127.0.0.1",
                proxy_port=59002,
                default_model="model-a",
                model_name="model-a",
                model_path="/path/a",
                ovms_version="2026.3",
            )

            service = OvmsLifecycleService(cfg)

            # 1. Enable model-c: adds to list without removing model-a or model-b
            service.enable_model("model-c", model_path="/path/c", dry_run=False, no_reload=True)
            cfg_after_enable = json.loads((root / "config.json").read_text(encoding="utf-8"))
            names = [m["config"]["name"] for m in cfg_after_enable["model_config_list"]]
            self.assertEqual(names, ["model-a", "model-b", "model-c"])
            self.assertEqual(cfg_after_enable["mediapipe_config_list"], [{"name": "pipeline-1"}])
            self.assertEqual(cfg_after_enable["custom_key"], "arc-gpu")

            # 2. Disable model-b: removes only model-b, keeping model-a and model-c
            service.disable_model("model-b", dry_run=False, no_reload=True)
            cfg_after_disable = json.loads((root / "config.json").read_text(encoding="utf-8"))
            names_after = [m["config"]["name"] for m in cfg_after_disable["model_config_list"]]
            self.assertEqual(names_after, ["model-a", "model-c"])
            self.assertEqual(cfg_after_disable["mediapipe_config_list"], [{"name": "pipeline-1"}])

    def test_rollback_restores_previous_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "model"
            model_dir.mkdir()

            (root / "config.json").write_text(
                json.dumps({"model_config_list": [{"config": {"name": "v1", "base_path": "p1"}}]}),
                encoding="utf-8",
            )
            (root / "config.env").write_text("MODEL_NAME=v1\nMODEL_PATH=p1\n", encoding="utf-8")

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=59000,
                ovms_grpc_port=59001,
                proxy_bind_host="127.0.0.1",
                proxy_port=59002,
                default_model="v1",
                model_name="v1",
                model_path="p1",
                ovms_version="2026.3",
            )

            service = OvmsLifecycleService(cfg)
            service.switch_model("v2", model_path=str(model_dir))

            # Rollback
            res = service.rollback()
            self.assertEqual("v1", res["rolled_back_to"])

            restored_json = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual("v1", restored_json["model_config_list"][0]["config"]["name"])
            self.assertIn("MODEL_NAME=v1", (root / "config.env").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
