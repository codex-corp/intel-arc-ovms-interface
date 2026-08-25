from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from tools.core.config import RuntimeConfig
from tools.core.env_resolver import resolve_ovms_environment
from tools.core.readiness import (
    check_tcp_port,
    probe_gateway_readiness,
    probe_ovms_readiness,
    wait_for_ovms_ready,
)


class ProcessState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING_OWNED = "RUNNING_OWNED"
    RUNNING_EXTERNAL = "RUNNING_EXTERNAL"
    PORT_CONFLICT = "PORT_CONFLICT"


class PortOccupiedError(RuntimeError):
    """Raised when a port is occupied by an unowned/incompatible third-party process."""
    pass


def _is_pid_alive(pid: int) -> bool:
    """Checks if a process ID is currently alive on Windows or POSIX."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _verify_process_signature(pid: int, expected_token: str) -> bool:
    """Validates that the running process with given PID belongs to the expected component."""
    if not _is_pid_alive(pid):
        return False
    try:
        import psutil
        p = psutil.Process(pid)
        if not p.is_running():
            return False
        cmdline = " ".join(p.cmdline()).lower()
        return expected_token.lower() in cmdline or expected_token.lower() in p.name().lower()
    except Exception:
        return _is_pid_alive(pid)


class ProcessManager:
    """Supervises OVMS and Gateway processes with verified persistent ownership and zero popups."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._owned_processes: Dict[str, subprocess.Popen] = {}
        self._state_dir = self.config.root / "artficats"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _pid_file_for(self, component: str) -> Path:
        return self._state_dir / f"{component}.pid"

    def _save_pid(self, component: str, pid: int) -> None:
        try:
            data = {"pid": pid, "component": component, "timestamp": time.time()}
            self._pid_file_for(component).write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _clear_pid(self, component: str) -> None:
        try:
            pid_file = self._pid_file_for(component)
            if pid_file.exists():
                pid_file.unlink()
        except Exception:
            pass

    def _get_verified_owned_pid(self, component: str) -> Optional[int]:
        """Retrieves and verifies the owned process PID from in-memory objects or persistent state files."""
        # 1. In-memory subprocess check
        proc = self._owned_processes.get(component)
        if proc is not None:
            if proc.poll() is None:
                return proc.pid
            else:
                del self._owned_processes[component]
                self._clear_pid(component)
                return None

        # 2. Persistent PID file check with executable/commandline verification
        pid_file = self._pid_file_for(component)
        if pid_file.exists():
            try:
                data = json.loads(pid_file.read_text(encoding="utf-8"))
                pid = int(data.get("pid", 0))
                expected = "ovms" if component == "ovms" else "proxy_server.py"
                if _is_pid_alive(pid) and _verify_process_signature(pid, expected):
                    return pid
                else:
                    self._clear_pid(component)
            except Exception:
                self._clear_pid(component)

        return None

    def get_status(self, component: str) -> ProcessState:
        """Determines process state, distinguishing between owned, adopted external, and conflicting processes."""
        owned_pid = self._get_verified_owned_pid(component)
        if owned_pid is not None:
            return ProcessState.RUNNING_OWNED

        if component == "ovms":
            port = self.config.ovms_port
            is_open = check_tcp_port(self.config.client_host, port)
            if not is_open:
                return ProcessState.STOPPED
            ovms_check = probe_ovms_readiness(port, client_host=self.config.client_host, timeout_sec=1.0)
            if ovms_check.reachable:
                return ProcessState.RUNNING_EXTERNAL
            return ProcessState.PORT_CONFLICT

        elif component == "gateway":
            port = self.config.proxy_port
            is_open = check_tcp_port(self.config.client_host, port)
            if not is_open:
                return ProcessState.STOPPED
            if probe_gateway_readiness(port, client_host=self.config.client_host, timeout_sec=1.0):
                return ProcessState.RUNNING_EXTERNAL
            return ProcessState.PORT_CONFLICT

        return ProcessState.STOPPED

    def start_ovms(
        self,
        timeout_sec: int = 45,
        expected_model: Optional[str] = None,
        wait_for_ready: bool = True,
        verbose: bool = False,
    ) -> ProcessState:
        """Starts ovms.exe as a supervised child process using cached setupvars environment."""
        current_state = self.get_status("ovms")
        if current_state in {ProcessState.RUNNING_OWNED, ProcessState.RUNNING_EXTERNAL}:
            return current_state
        if current_state == ProcessState.PORT_CONFLICT:
            raise PortOccupiedError(
                f"OVMS port {self.config.ovms_port} is occupied by an unowned, non-OVMS process."
            )

        ovms_exe = self.config.ovms_dir / "ovms.exe"
        if not ovms_exe.exists():
            raise FileNotFoundError(f"OVMS binary not found at: {ovms_exe}")

        env = resolve_ovms_environment(self.config.ovms_dir)
        env["OPENVINO_LOG_LEVEL"] = "INFO" if verbose else "WARNING"

        cmd = [
            str(ovms_exe),
            "--config_path",
            str(self.config.config_json),
            "--port",
            str(self.config.ovms_grpc_port),
            "--rest_port",
            str(self.config.ovms_port),
            "--log_level",
            "INFO" if verbose else "ERROR",
        ]

        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.config.root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._owned_processes["ovms"] = proc
        self._save_pid("ovms", proc.pid)

        if wait_for_ready:
            ready = wait_for_ovms_ready(
                rest_port=self.config.ovms_port,
                client_host=self.config.client_host,
                timeout_sec=timeout_sec,
                expected_model=expected_model,
            )
            if not ready:
                self.stop_component("ovms")
                raise TimeoutError(f"OVMS did not become ready on port {self.config.ovms_port} within {timeout_sec}s.")

        return ProcessState.RUNNING_OWNED

    def start_gateway(self, wait_for_ready: bool = True, timeout_sec: int = 15) -> ProcessState:
        """Starts proxy_server.py as an isolated, supervised child process."""
        current_state = self.get_status("gateway")
        if current_state in {ProcessState.RUNNING_OWNED, ProcessState.RUNNING_EXTERNAL}:
            return current_state
        if current_state == ProcessState.PORT_CONFLICT:
            raise PortOccupiedError(
                f"Gateway port {self.config.proxy_port} is occupied by an unowned process."
            )

        script = self.config.root / "proxy_server.py"
        if not script.exists():
            raise FileNotFoundError(f"Gateway script not found at: {script}")

        cmd = [
            str(self.config.python_exe),
            str(script),
        ]

        proc_env = os.environ.copy()
        proc_env["PYTHONIOENCODING"] = "utf-8"
        proc_env["PYTHONUTF8"] = "1"
        proc_env["PYTHONUNBUFFERED"] = "1"

        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.config.root),
            env=proc_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._owned_processes["gateway"] = proc
        self._save_pid("gateway", proc.pid)

        if wait_for_ready:
            start_time = time.time()
            while time.time() - start_time < timeout_sec:
                if probe_gateway_readiness(self.config.proxy_port, client_host=self.config.client_host, timeout_sec=1.0):
                    return ProcessState.RUNNING_OWNED
                time.sleep(0.5)

            # Timeout reached without readiness: stop and raise
            self.stop_component("gateway")
            raise TimeoutError(f"Gateway did not become ready on port {self.config.proxy_port} within {timeout_sec}s.")

        return ProcessState.RUNNING_OWNED

    def stop_component(self, component: str) -> bool:
        """Stops ONLY processes verified to be owned by this studio. Never terminates unrelated processes."""
        pid = self._get_verified_owned_pid(component)
        if not pid:
            return False

        # Terminate in-memory object if available
        proc = self._owned_processes.pop(component, None)
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # Terminate by verified PID
        if _is_pid_alive(pid):
            if sys.platform == "win32":
                try:
                    subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True, timeout=5)
                except Exception:
                    pass
            else:
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass

        self._clear_pid(component)
        return True
