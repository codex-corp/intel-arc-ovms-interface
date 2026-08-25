from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.core import cli
from tools.core.config import RuntimeConfig


class Phase6CliTests(unittest.TestCase):
    """Unit tests for Phase 6: Core CLI Interface and command parsing."""

    def test_cli_status_json(self):
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("tools.core.cli.probe_ovms_readiness") as mock_ovms:
                    mock_ovms.return_value = MagicMock(reachable=False, models=[], is_ready=False, error="offline")
                    with patch("tools.core.cli.probe_gateway_readiness", return_value=False):
                        with patch("sys.stdout", new=io.StringIO()) as fake_out:
                            ret = cli.main(["status", "--json"])
                            self.assertEqual(ret, 0)
                            data = json.loads(fake_out.getvalue())
                            self.assertIn("ovms", data)
                            self.assertIn("gateway", data)
                            self.assertIn("models", data)
                            self.assertFalse(data["ovms"]["reachable"])

    def test_cli_list_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_file = root / "models_manifest.json"
            manifest_file.write_text(
                json.dumps({
                    "version": "1.0",
                    "models": {
                        "qwen": {"repo_id": "OpenVINO/qwen-int4-ov", "default_name": "qwen"}
                    },
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["list", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertIn("models", data)
                    self.assertTrue(len(data["models"]) >= 1)
                    self.assertEqual(data["models"][0]["name"], "qwen")

    def test_cli_switch_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "qwen-new"
            model_dir.mkdir()

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path("python.exe"),
                ovms_dir=root / "ovms",
                ovms_port=8000,
                ovms_grpc_port=9000,
                proxy_bind_host="127.0.0.1",
                proxy_port=8001,
                default_model="qwen-old",
                model_name="qwen-old",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["switch", "qwen-new", "--path", str(model_dir), "--dry-run", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertTrue(data.get("dry_run"))
                    self.assertEqual(data.get("to_model"), "qwen-new")

    def test_cli_test_ready_json(self):
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("tools.core.cli.wait_for_ovms_ready", return_value=True):
                    with patch("sys.stdout", new=io.StringIO()) as fake_out:
                        ret = cli.main(["test-ready", "--json"])
                        self.assertEqual(ret, 0)
                        data = json.loads(fake_out.getvalue())
                        self.assertTrue(data["ready"])

    def test_cli_configure_and_enable_flags(self):
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                # configure --dry-run
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["configure", "test-m", "--path", "/models/test-m", "--dry-run", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertTrue(data.get("dry_run"))
                    self.assertEqual(data.get("model"), "test-m")

                # enable with --name and --dry-run
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["enable", "--name", "test-m", "--path", "/models/test-m", "--dry-run", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertTrue(data.get("dry_run"))

    def test_cli_disable_and_native_list_flags(self):
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                # native-list --json
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["native-list", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertIn("repository_path", data)

                # disable --name --dry-run
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["disable", "--name", "test-m", "--dry-run", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertTrue(data.get("dry_run"))

    def test_cli_reload_and_rollback_flags(self):
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
                default_model="qwen",
                model_name="qwen",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("tools.core.lifecycle.OvmsLifecycleService.reload", return_value={"reloaded": True}) as mock_reload:
                    with patch("sys.stdout", new=io.StringIO()) as fake_out:
                        ret = cli.main(["reload", "--timeout", "15", "--json"])
                        self.assertEqual(ret, 0)
                        mock_reload.assert_called_once_with(timeout_sec=15, config_path=None)

                with patch("tools.core.lifecycle.OvmsLifecycleService.rollback", return_value={"rolled_back_to": "m1"}) as mock_rb:
                    with patch("sys.stdout", new=io.StringIO()) as fake_out:
                        ret = cli.main(["rollback", "--target", str(root / "backup.json"), "--json"])
                        self.assertEqual(ret, 0)
                        mock_rb.assert_called_once_with(target_backup=str(root / "backup.json"), config_path=None)


if __name__ == "__main__":
    unittest.main()
