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


def fetch_models(rest_port: int, timeout_sec: int = 3) -> OvmsStatus:
    url = f"http://localhost:{rest_port}/v3/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            model_ids = [str(m.get("id")) for m in raw.get("data", []) if isinstance(m, dict) and m.get("id")]
            return OvmsStatus(reachable=True, models=model_ids, raw=raw)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return OvmsStatus(reachable=False, models=[], raw=None, error=str(exc))

