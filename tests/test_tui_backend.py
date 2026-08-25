import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.tui.backend import format_management_result, load_runtime_config


class TuiBackendTests(unittest.TestCase):
    def test_runtime_config_prefers_config_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.env.example").write_text(
                "OVMS_PORT=8000\nPROXY_PORT=8001\nPROXY_HOST=127.0.0.1\nMODEL_NAME=example\nPYTHON_EXE=.\\.venv\\Scripts\\python.exe\n",
                encoding="utf-8",
            )
            (root / "config.env").write_text(
                "OVMS_PORT=9100\nPROXY_PORT=9101\nMODEL_NAME=local-model\n",
                encoding="utf-8",
            )

            config = load_runtime_config(root)

            self.assertEqual(9100, config.ovms_port)
            self.assertEqual(9101, config.proxy_port)
            self.assertEqual("127.0.0.1", config.proxy_host)
            self.assertEqual("local-model", config.model_name)
            self.assertEqual("http://127.0.0.1:9101/v3", config.gateway_base_url)

    def test_runtime_config_handles_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.env").write_text(
                "\ufeffOVMS_PORT=8123\nPROXY_PORT=8124\n",
                encoding="utf-8",
            )

            config = load_runtime_config(root)

            self.assertEqual(8123, config.ovms_port)
            self.assertEqual(8124, config.proxy_port)

    def test_management_result_combines_stdout_and_stderr(self):
        result = subprocess.CompletedProcess(
            args=["powershell.exe"],
            returncode=1,
            stdout="normal output\n",
            stderr="error output\n",
        )

        self.assertEqual(
            "normal output\nerror output",
            format_management_result(result),
        )

    def test_management_result_reports_empty_output(self):
        result = subprocess.CompletedProcess(
            args=["powershell.exe"],
            returncode=0,
            stdout="",
            stderr="",
        )

        self.assertEqual("Command exited with code 0.", format_management_result(result))


if __name__ == "__main__":
    unittest.main()
