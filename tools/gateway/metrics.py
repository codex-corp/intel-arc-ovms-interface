from __future__ import annotations
from dataclasses import dataclass, field
import time

@dataclass
class RequestMetrics:
    started_at: float = field(default_factory=time.perf_counter)
    first_chunk_at: float | None = None
    chunks: int = 0
    completion_tokens: int | None = None

    def record_chunk(self) -> None:
        now = time.perf_counter()
        if self.first_chunk_at is None:
            self.first_chunk_at = now
        self.chunks += 1

    @property
    def ttft(self) -> float | None:
        return None if self.first_chunk_at is None else self.first_chunk_at - self.started_at

    def finish(self) -> dict:
        elapsed = max(time.perf_counter() - self.started_at, 1e-9)
        return {
            "elapsed_s": elapsed,
            "ttft_s": self.ttft,
            "completion_tokens": self.completion_tokens,
            "tokens_per_s": (self.completion_tokens / elapsed) if self.completion_tokens is not None else None,
            "stream_chunks": self.chunks,
            "chunks_per_s": self.chunks / elapsed,
        }
