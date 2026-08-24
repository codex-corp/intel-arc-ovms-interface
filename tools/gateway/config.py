from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class GatewayConfig:
    upstream: str
    host: str
    port: int
    compatibility_profile: str
    log_prompt_preview: bool

def load_gateway_config(root: Path) -> GatewayConfig:
    data = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    server = data["server"]
    proxy = data["proxy"]
    return GatewayConfig(
        upstream=f"http://127.0.0.1:{int(server['rest_port'])}",
        host=str(proxy.get("host", "127.0.0.1")),
        port=int(proxy.get("port", 8001)),
        compatibility_profile=str(proxy.get("compatibility_profile", "passthrough")),
        log_prompt_preview=bool(proxy.get("log_prompt_preview", False)),
    )
