from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.core import cli
from tools.core.config import RuntimeConfig, load_core_config
from tools.core.lifecycle import OvmsLifecycleService
from tools.core.manifest import discover_all_models, is_model_weights_ready, load_manifest
from tools.core.readiness import check_tcp_port, probe_ovms_readiness


class Phase7IntegrationContractTests(unittest.TestCase):
    """Integration and contract test suite validating Python Core services with temporary state/mocks."""

    def test_e2e_runtime_config_and_manifest_coherence(self):
        cfg = load_core_config()
        self.assertIsNotNone(cfg.root)
        self.assertTrue(cfg.manifest_path.exists(), "models_manifest.json must exist in root")

        catalog = load_manifest(cfg.manifest_path)
        self.assertTrue(len(catalog) > 0, "Manifest catalog should contain verified models")

        models = discover_all_models(cfg)
        self.assertTrue(len(models) >= len(catalog))

        for name, info in models.items():
            self.assertIsNotNone(info.name)
            if info.is_downloaded:
                self.assertIsNotNone(info.local_path)
            if info.catalog_entry:
                self.assertTrue(bool(info.catalog_entry.repo_id))

    def test_e2e_multi_model_config_preservation_and_duplicate_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_file = root / "config.json"
            cfg_file.write_text(
                json.dumps({
                    "model_config_list": [
                        {"config": {"name": "model-1", "base_path": "/path/1"}},
                        {"config": {"name": "model-2", "base_path": "/path/2"}},
                    ],
                    "mediapipe_config_list": [{"name": "pipeline-1"}],
                }),
                encoding="utf-8",
            )
            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=8000,
                ovms_grpc_port=9000,
                proxy_bind_host="127.0.0.1",
                proxy_port=8001,
                default_model="model-1",
                model_name="model-1",
                model_path="/path/1",
                ovms_version="2026.3",
            )
            service = OvmsLifecycleService(cfg)
            res = service.enable_model("model-3", model_path="/path/3", dry_run=False, no_reload=True)
            self.assertTrue(res["changed"])

            updated = json.loads(cfg_file.read_text(encoding="utf-8"))
            names = [m["config"]["name"] for m in updated["model_config_list"]]
            self.assertEqual(["model-1", "model-2", "model-3"], names)
            self.assertEqual(len(names), len(set(names)), "Model names must be unique")
            self.assertEqual([{"name": "pipeline-1"}], updated["mediapipe_config_list"])

    def test_e2e_cli_json_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=8000,
                ovms_grpc_port=9000,
                proxy_bind_host="127.0.0.1",
                proxy_port=8001,
                default_model="default",
                model_name="default",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("tools.core.cli.probe_ovms_readiness") as mock_ovms:
                    mock_ovms.return_value = MagicMock(reachable=False, models=[], is_ready=False, error="offline")
                    with patch("sys.stdout", new=io.StringIO()) as fake_out:
                        ret = cli.main(["status", "--json"])
                        self.assertEqual(ret, 0)
                        status_data = json.loads(fake_out.getvalue())
                        self.assertIn("ovms", status_data)
                        self.assertIn("gateway", status_data)
                        self.assertIn("models", status_data)

                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["list", "--json"])
                    self.assertEqual(ret, 0)
                    list_data = json.loads(fake_out.getvalue())
                    self.assertIn("models", list_data)
                    self.assertIsInstance(list_data["models"], list)

    def test_e2e_lifecycle_service_atomic_rollback_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_json = root / "config.json"
            config_json.write_text(
                json.dumps({
                    "model_config_list": [
                        {"config": {"name": "working-model", "base_path": str(root / "working")}}
                    ]
                }),
                encoding="utf-8",
            )

            working_dir = root / "working"
            working_dir.mkdir()
            (working_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (working_dir / "openvino_model.bin").write_bytes(b"\x00" * 16)

            target_dir = root / "target"
            target_dir.mkdir()
            (target_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (target_dir / "openvino_model.bin").write_bytes(b"\x00" * 16)

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=8000,
                ovms_grpc_port=9000,
                proxy_bind_host="127.0.0.1",
                proxy_port=8001,
                default_model="working-model",
                model_name="working-model",
                model_path=str(working_dir),
                ovms_version="2026.3",
            )

            service = OvmsLifecycleService(cfg)

            with patch("tools.core.lifecycle.probe_ovms_readiness") as mock_probe:
                mock_probe.return_value.reachable = True
                with patch("tools.core.lifecycle.reload_config"):
                    with patch("tools.core.lifecycle.wait_for_ovms_ready", return_value=False):
                        with self.assertRaises(TimeoutError):
                            service.switch_model("target-model", model_path=str(target_dir), timeout_sec=1)

            restored = json.loads(config_json.read_text(encoding="utf-8"))
            self.assertEqual(
                restored["model_config_list"][0]["config"]["name"],
                "working-model",
                "Lifecycle service must roll back config.json upon reload failure",
            )


if __name__ == "__main__":
    unittest.main()
