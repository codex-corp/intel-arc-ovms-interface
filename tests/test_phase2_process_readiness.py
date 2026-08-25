from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tools.core.config import RuntimeConfig
from tools.core.env_resolver import clear_environment_cache, resolve_ovms_environment
from tools.core.process_manager import ProcessManager, ProcessState
from tools.core.readiness import check_tcp_port, probe_ovms_readiness


class Phase2ProcessAndReadinessTests(unittest.TestCase):
    """Unit tests for Phase 2: OVMS Environment Resolver + Process Supervisor + Readiness."""

    def setUp(self):
        clear_environment_cache()

    def test_env_resolver_fallback_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            ovms_dir = Path(tmp) / "ovms"
            ovms_dir.mkdir()

            env1 = resolve_ovms_environment(ovms_dir)
            self.assertIsInstance(env1, dict)
            self.assertIn("PATH", env1)

            # Second call retrieves cached environment
            env2 = resolve_ovms_environment(ovms_dir)
            self.assertEqual(env1, env2)

            clear_environment_cache()

    def test_readiness_probes_tcp_ports(self):
        # Find a free ephemeral port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(5)
        port = sock.getsockname()[1]

        try:
            self.assertTrue(check_tcp_port("127.0.0.1", port, timeout_sec=1.0))
            self.assertTrue(check_tcp_port("0.0.0.0", port, timeout_sec=1.0))  # Normalized to 127.0.0.1
        finally:
            sock.close()

        # Closed port returns False
        self.assertFalse(check_tcp_port("127.0.0.1", port, timeout_sec=0.2))

    def test_process_manager_strict_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = RuntimeConfig(
                root=root,
                python_exe=Path(sys.executable),
                ovms_dir=root / "ovms",
                ovms_port=59123,
                ovms_grpc_port=59124,
                proxy_bind_host="127.0.0.1",
                proxy_port=59125,
                default_model="dummy",
                model_name="dummy",
                model_path="",
                ovms_version="2026.3",
            )

            mgr = ProcessManager(cfg)
            self.assertEqual(ProcessState.STOPPED, mgr.get_status("ovms"))
            self.assertEqual(ProcessState.STOPPED, mgr.get_status("gateway"))

            # Cannot stop unowned process
            self.assertFalse(mgr.stop_component("ovms"))

            # Start a dummy owned child process
            dummy_proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            mgr._owned_processes["gateway"] = dummy_proc
            self.assertEqual(ProcessState.RUNNING_OWNED, mgr.get_status("gateway"))

            # Stopping owned process succeeds and resets state
            self.assertTrue(mgr.stop_component("gateway"))
            self.assertEqual(ProcessState.STOPPED, mgr.get_status("gateway"))

    def test_gateway_launch_environment_enforces_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proxy_script = root / "proxy_server.py"
            proxy_script.write_text("import time; time.sleep(1)", encoding="utf-8")

            cfg = RuntimeConfig(
                root=root,
                python_exe=Path(sys.executable),
                ovms_dir=root / "ovms",
                ovms_port=59123,
                ovms_grpc_port=59124,
                proxy_bind_host="127.0.0.1",
                proxy_port=59125,
                default_model="dummy",
                model_name="dummy",
                model_path="",
                ovms_version="2026.3",
            )

            mgr = ProcessManager(cfg)
            from unittest.mock import patch
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = mock_popen.return_value
                mock_proc.pid = 1234
                mock_proc.poll.return_value = None
                mgr.start_gateway(wait_for_ready=False)

                self.assertTrue(mock_popen.called)
                _, kwargs = mock_popen.call_args
                env = kwargs.get("env", {})
                self.assertEqual(env.get("PYTHONUTF8"), "1", "ProcessManager must enforce PYTHONUTF8=1 for Gateway")
                self.assertEqual(env.get("PYTHONIOENCODING"), "utf-8", "ProcessManager must enforce PYTHONIOENCODING=utf-8")
                self.assertEqual(env.get("PYTHONUNBUFFERED"), "1", "ProcessManager must enforce PYTHONUNBUFFERED=1")

    def test_process_manager_persistent_pid_file_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = RuntimeConfig(
                root=root,
                python_exe=Path(sys.executable),
                ovms_dir=root / "ovms",
                ovms_port=59123,
                ovms_grpc_port=59124,
                proxy_bind_host="127.0.0.1",
                proxy_port=59125,
                default_model="dummy",
                model_name="dummy",
                model_path="",
                ovms_version="2026.3",
            )

            mgr1 = ProcessManager(cfg)
            dummy_proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(10) # proxy_server.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                # Save PID to persistent state file
                mgr1._save_pid("gateway", dummy_proc.pid)

                # A new ProcessManager instance in another CLI invocation sees the PID file
                mgr2 = ProcessManager(cfg)
                self.assertEqual(dummy_proc.pid, mgr2._get_verified_owned_pid("gateway"))

                # Stopping via mgr2 cleans up PID file
                self.assertTrue(mgr2.stop_component("gateway"))
                self.assertFalse(mgr2._pid_file_for("gateway").exists())
            finally:
                if dummy_proc.poll() is None:
                    dummy_proc.kill()


if __name__ == "__main__":
    unittest.main()
