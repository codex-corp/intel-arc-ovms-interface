from __future__ import annotations
import uuid

def adapt_sse_payload(payload: dict, profile: str) -> dict:
    """Apply only client-specific compatibility changes; preserve reasoning/tool fields by default."""
    if profile in {"jetbrains", "legacy"} and "id" not in payload:
        payload = dict(payload)
        payload["id"] = f"chatcmpl-{uuid.uuid4()}"
    if profile == "legacy":
        payload = dict(payload)
        choices = []
        for choice in payload.get("choices", []):
            choice = dict(choice)
            delta = dict(choice.get("delta", {}))
            delta.pop("reasoning_content", None)
            choice["delta"] = delta
            choices.append(choice)
        payload["choices"] = choices
    return payload
