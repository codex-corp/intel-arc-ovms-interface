from __future__ import annotations

import os
import subprocess
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


class ProcessManager:
    """Supervises OVMS and Gateway processes with strict process ownership and zero visible popups."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._owned_processes: Dict[str, subprocess.Popen] = {}

    def get_status(self, component: str) -> ProcessState:
        """Determines process state, distinguishing between owned, adopted external, and conflicting processes."""
        proc = self._owned_processes.get(component)
        if proc is not None:
            if proc.poll() is None:
                return ProcessState.RUNNING_OWNED
            else:
                del self._owned_processes[component]

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
        env["OPENVINO_LOG_LEVEL"] = "WARNING"

        cmd = [
            str(ovms_exe),
            "--config_path",
            str(self.config.config_json),
            "--port",
            str(self.config.ovms_grpc_port),
            "--rest_port",
            str(self.config.ovms_port),
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

        if wait_for_ready:
            deadline = 0.0
            import time
            start_time = time.time()
            while time.time() - start_time < timeout_sec:
                if probe_gateway_readiness(self.config.proxy_port, client_host=self.config.client_host, timeout_sec=1.0):
                    return ProcessState.RUNNING_OWNED
                time.sleep(0.5)

        return ProcessState.RUNNING_OWNED

    def stop_component(self, component: str) -> bool:
        """Stops ONLY processes owned by this manager. Never terminates third-party/unowned processes."""
        proc = self._owned_processes.get(component)
        if not proc:
            return False

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            return True
        except OSError:
            return False
        finally:
            if component in self._owned_processes:
                del self._owned_processes[component]

    def stop_all_owned(self) -> None:
        """Terminates all owned child processes during application shutdown."""
        for comp in list(self._owned_processes.keys()):
            self.stop_component(comp)
