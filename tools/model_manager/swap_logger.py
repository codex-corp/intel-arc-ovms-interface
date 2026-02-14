from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def append_event(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": int(time.time()), **payload}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")

