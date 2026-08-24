from __future__ import annotations
import asyncio
import json
from pathlib import Path
from aiohttp import ClientConnectorError, ClientSession, ClientTimeout, web
from .adapters import adapt_sse_payload
from .config import load_gateway_config
from .metrics import RequestMetrics

ROOT = Path(__file__).resolve().parents[2]
CFG = load_gateway_config(ROOT)

async def handle(request: web.Request) -> web.StreamResponse:
    target = CFG.upstream + request.rel_url.path_qs
    body = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    metrics = RequestMetrics()
    try:
        async with request.app["session"].request(request.method, target, headers=headers, data=body) as upstream:
            response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
            for k, v in upstream.headers.items():
                if k.lower() not in {"transfer-encoding", "content-length"}:
                    response.headers[k] = v
            await response.prepare(request)
            is_sse = "text/event-stream" in upstream.headers.get("Content-Type", "")
            if not is_sse:
                async for chunk in upstream.content.iter_any():
                    await response.write(chunk)
                return response
            buffer = ""
            async for chunk in upstream.content.iter_any():
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            payload = adapt_sse_payload(json.loads(line[6:]), CFG.compatibility_profile)
                            usage = payload.get("usage") or {}
                            if isinstance(usage.get("completion_tokens"), int):
                                metrics.completion_tokens = usage["completion_tokens"]
                            metrics.record_chunk()
                            line = "data: " + json.dumps(payload, ensure_ascii=False)
                        except (ValueError, TypeError):
                            pass
                    await response.write((line + "\n").encode("utf-8"))
            if buffer:
                await response.write(buffer.encode("utf-8"))
            result = metrics.finish()
            tps = f"{result['tokens_per_s']:.1f} tok/s" if result["tokens_per_s"] is not None else f"{result['chunks_per_s']:.1f} chunks/s"
            ttft = f"{result['ttft_s']:.3f}s" if result["ttft_s"] is not None else "n/a"
            print(f"{request.method} {request.path} -> {upstream.status} | TTFT {ttft} | {tps}", flush=True)
            return response
    except asyncio.TimeoutError:
        return web.Response(text="Gateway Error: upstream timeout", status=504)
    except ClientConnectorError:
        return web.Response(text="Gateway Error: OVMS unavailable", status=502)

async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession(timeout=ClientTimeout(total=300, connect=10))

async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle)
    return app

def main() -> None:
    print(f"Compatibility gateway {CFG.host}:{CFG.port} -> {CFG.upstream} [{CFG.compatibility_profile}]")
    web.run_app(create_app(), host=CFG.host, port=CFG.port, access_log=None)
