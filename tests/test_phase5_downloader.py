from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.core.config import RuntimeConfig
from tools.core.downloader import pull_model


class Phase5DownloaderTests(unittest.TestCase):
    """Unit tests for Phase 5: Native Pull / Downloader Engine with Progress Reporting."""

    def test_pull_model_uses_manifest_repo_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_file = root / "models_manifest.json"
            manifest_file.write_text(
                json.dumps({
                    "version": "1.0",
                    "models": {
                        "test-model": {
                            "repo_id": "OpenVINO/test-model-ov",
                            "default_name": "test-model",
                        }
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
                default_model="test-model",
                model_name="test-model",
                model_path="",
                ovms_version="2026.3",
            )

            progress_messages = []

            def record_progress(msg: str) -> None:
                progress_messages.append(msg)

            dest_dir = root / "models" / "test-model"

            # Mock huggingface_hub snapshot_download
            def fake_download(repo_id: str, local_dir: str):
                p = Path(local_dir)
                p.mkdir(parents=True, exist_ok=True)
                (p / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
                (p / "openvino_model.bin").write_bytes(b"\x00" * 32)

            with patch("huggingface_hub.snapshot_download", side_effect=fake_download):
                result_path = pull_model(
                    cfg,
                    "test-model",
                    on_progress=record_progress,
                    destination_override=dest_dir,
                )

                self.assertEqual(dest_dir.resolve(), result_path.resolve())
                self.assertTrue((dest_dir / "openvino_model.bin").exists())
                self.assertTrue(len(progress_messages) > 0)
                self.assertTrue(any("Connecting to repository" in m or "Downloading" in m for m in progress_messages))

    def test_pull_model_raises_when_weights_missing_after_download(self):
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
                default_model="missing-weights",
                model_name="missing-weights",
                model_path="",
                ovms_version="2026.3",
            )

            def fake_incomplete_download(repo_id: str, local_dir: str):
                p = Path(local_dir)
                p.mkdir(parents=True, exist_ok=True)
                (p / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
                # Intentionally missing binary weights!

            with patch("huggingface_hub.snapshot_download", side_effect=fake_incomplete_download):
                with self.assertRaises(RuntimeError) as ctx:
                    pull_model(cfg, "missing-weights", destination_override=root / "m")
                self.assertIn("required binary weights (.bin/.gguf) were not found", str(ctx.exception))

    def test_get_dir_size_mb_sums_all_files(self):
        from tools.core.downloader import _get_dir_size_mb

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "file1.bin").write_bytes(b"\x00" * (1024 * 1024))  # 1 MB
            (root / "file2.bin").write_bytes(b"\x00" * (2 * 1024 * 1024))  # 2 MB
            sub = root / "subdir"
            sub.mkdir()
            (sub / "file3.bin").write_bytes(b"\x00" * (3 * 1024 * 1024))  # 3 MB

            total_mb = _get_dir_size_mb(root)
            self.assertAlmostEqual(6.0, total_mb, places=1)


if __name__ == "__main__":
    unittest.main()
