from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def load_registry(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models", {})
    return {str(k): str(v) for k, v in models.items()}

