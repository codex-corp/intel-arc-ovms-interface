from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class OvmsReadinessResult:
    reachable: bool
    models: List[str]
    is_ready: bool
    error: Optional[str] = None


def check_tcp_port(host: str, port: int, timeout_sec: float = 0.8) -> bool:
    """Probes if a TCP port is open and accepting socket connections."""
    target_host = "127.0.0.1" if host in {"0.0.0.0", "", "::", "localhost"} else host
    try:
        with socket.create_connection((target_host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def probe_ovms_readiness(
    rest_port: int,
    client_host: str = "127.0.0.1",
    timeout_sec: float = 2.0,
    expected_model: Optional[str] = None,
) -> OvmsReadinessResult:
    """Probes OVMS /v3/models or /v1/config to verify if the server is healthy and models are serving."""
    target_host = "127.0.0.1" if client_host in {"0.0.0.0", "", "::", "localhost"} else client_host
    url = f"http://{target_host}:{rest_port}/v3/models"

    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            models = [str(m.get("id")) for m in raw.get("data", []) if isinstance(m, dict) and m.get("id")]
            is_ready = True
            if expected_model and expected_model not in models:
                is_ready = False
            return OvmsReadinessResult(reachable=True, models=models, is_ready=is_ready)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return OvmsReadinessResult(reachable=False, models=[], is_ready=False, error=str(exc))


def wait_for_ovms_ready(
    rest_port: int,
    client_host: str = "127.0.0.1",
    timeout_sec: int = 45,
    expected_model: Optional[str] = None,
    poll_interval: float = 1.0,
) -> bool:
    """Polls OVMS until it reports healthy readiness status or the timeout expires."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        res = probe_ovms_readiness(
            rest_port=rest_port,
            client_host=client_host,
            timeout_sec=2.0,
            expected_model=expected_model,
        )
        if res.is_ready:
            return True
        time.sleep(poll_interval)
    return False


def probe_gateway_readiness(
    proxy_port: int,
    client_host: str = "127.0.0.1",
    timeout_sec: float = 2.0,
) -> bool:
    """Checks if the OpenAI Gateway proxy is reachable and responding with application-level HTTP 200."""
    target_host = "127.0.0.1" if client_host in {"0.0.0.0", "", "::", "localhost"} else client_host
    for path in ["/v3/models", "/v1/models"]:
        url = f"http://{target_host}:{proxy_port}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OvmsStudioProbe/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, dict) and "data" in data:
                        return True
        except Exception:
            continue
    return False
