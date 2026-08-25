from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

import aiohttp

from tools.core.config import RuntimeConfig
from tools.core.readiness import check_tcp_port


@dataclass
class ChatDelta:
    content: str = ""
    reasoning: str = ""
    finish_reason: Optional[str] = None


class ChatClient:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[ChatDelta]:
        base_url = (
            self.config.gateway_base_url
            if check_tcp_port(self.config.client_host, self.config.proxy_port)
            else f"http://127.0.0.1:{self.config.ovms_port}/v3"
        )
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
        }
        timeout = aiohttp.ClientTimeout(total=600, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    detail = await response.text()
                    raise RuntimeError(f"Gateway returned HTTP {response.status}: {detail[:500]}")

                buffer = ""
                async for raw in response.content.iter_any():
                    buffer += raw.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        value = line[5:].strip()
                        if value == "[DONE]":
                            return
                        try:
                            data = json.loads(value)
                        except json.JSONDecodeError:
                            continue

                        for choice in data.get("choices", []):
                            delta = choice.get("delta") or {}
                            content = delta.get("content") or ""
                            reasoning = delta.get("reasoning_content") or ""
                            finish_reason = choice.get("finish_reason")
                            if content or reasoning or finish_reason:
                                yield ChatDelta(
                                    content=str(content),
                                    reasoning=str(reasoning),
                                    finish_reason=finish_reason,
                                )
