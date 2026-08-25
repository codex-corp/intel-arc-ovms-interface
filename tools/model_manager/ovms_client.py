from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class OvmsStatus:
    reachable: bool
    models: List[str]
    raw: Dict[str, Any] | None
    error: str | None = None


def fetch_models(rest_port: int, timeout_sec: int = 2) -> OvmsStatus:
    url = f"http://127.0.0.1:{rest_port}/v3/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            model_ids = [str(m.get("id")) for m in raw.get("data", []) if isinstance(m, dict) and m.get("id")]
            return OvmsStatus(reachable=True, models=model_ids, raw=raw)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return OvmsStatus(reachable=False, models=[], raw=None, error=str(exc))


def reload_config(rest_port: int, timeout_sec: int = 10) -> bool:
    """Send POST /v1/config/reload to trigger dynamic config reloading in OVMS."""
    url = f"http://127.0.0.1:{rest_port}/v1/config/reload"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status in (200, 201)
    except Exception:
        return False
