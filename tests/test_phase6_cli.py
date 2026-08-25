from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.core import cli
from tools.core.config import RuntimeConfig


class Phase6CliTests(unittest.TestCase):
    """Unit tests for Phase 6: First-Class Core CLI (cli.py)."""

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
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["status", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertIn("ovms", data)
                    self.assertIn("gateway", data)
                    self.assertIn("models", data)
                    self.assertEqual(data["ovms"]["rest_port"], 8000)

    def test_cli_list_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_file = root / "models_manifest.json"
            manifest_file.write_text(
                json.dumps({
                    "version": "1.0",
                    "models": {
                        "model-a": {"repo_id": "OpenVINO/model-a-ov", "default_name": "model-a"},
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
                default_model="model-a",
                model_name="model-a",
                model_path="",
                ovms_version="2026.3",
            )

            with patch("tools.core.cli.load_core_config", return_value=cfg):
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["list", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertIn("models", data)
                    self.assertTrue(any(m["name"] == "model-a" for m in data["models"]))

    def test_cli_switch_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "models" / "qwen-new"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (model_dir / "openvino_model.bin").write_bytes(b"\x00" * 32)

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
                    self.assertIn("models", data)

                # disable --name --dry-run
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    ret = cli.main(["disable", "--name", "test-m", "--dry-run", "--json"])
                    self.assertEqual(ret, 0)
                    data = json.loads(fake_out.getvalue())
                    self.assertTrue(data.get("dry_run"))


if __name__ == "__main__":
    unittest.main()
