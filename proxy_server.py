import os
import aiohttp
from aiohttp import web
import json
import uuid
import asyncio
import sys
import time
import subprocess

# Load config.env (same file used by PowerShell scripts)
def load_config():
    config = {}
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.env')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config

_cfg = load_config()
TARGET_URL = f"http://localhost:{_cfg.get('OVMS_PORT', '8000')}"
PORT = int(_cfg.get('PROXY_PORT', '8001'))

# ── Telemetry ──────────────────────────────────────────────
_base_dir = os.path.dirname(os.path.abspath(__file__))
_xpu_smi = os.path.join(_base_dir, "xpu-smi", "xpu-smi.exe")
_has_xpu = os.path.exists(_xpu_smi)

_token_count = 0
_token_start = None
_last_tps = 0.0
_request_count = 0
_completion_id = 0
_total_tokens = 0
_boot_time = time.time()

def record_token():
    global _token_count, _token_start, _last_tps
    if _token_start is None:
        _token_start = time.time()
        _token_count = 0
    _token_count += 1
    elapsed = time.time() - _token_start
    if elapsed > 0:
        _last_tps = _token_count / elapsed

def reset_tokens():
    global _token_count, _token_start, _last_tps
    _token_start = time.time()
    _token_count = 0
    _last_tps = 0.0

def get_gpu_metrics():
    if not _has_xpu:
        return None
    try:
        result = subprocess.run(
            [_xpu_smi, "dump", "-d", "0", "-m", "0,1,5,18,31", "-n", "1"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            for line in reversed(result.stdout.strip().split('\n')):
                parts = line.split(',')
                if len(parts) >= 7 and ':' in parts[0]:
                    try:
                        return {
                            "gpu": float(parts[2].strip()),
                            "power": float(parts[3].strip()),
                            "vram": float(parts[5].strip()),
                            "compute": float(parts[6].strip()),
                        }
                    except ValueError:
                        continue
    except:
        pass
    return None

def _update_header():
    """Update the fixed top bar (lines 1-3) without disturbing the log scroll area."""
    uptime = int(time.time() - _boot_time)
    h, m = divmod(uptime // 60, 60)
    up_str = f"{h}h{m:02d}m" if h else f"{m}m"

    hw = get_gpu_metrics()
    if hw:
        status = (
            f" GPU {hw['gpu']:3.0f}%  │"
            f"  Power {hw['power']:5.1f}W  │"
            f"  VRAM {hw['vram']:5.0f} MiB  │"
            f"  Compute {hw['compute']:3.0f}%  │"
            f"  TPS {_last_tps:5.1f}  │"
            f"  Reqs {_request_count}  │"
            f"  ↑{up_str}"
        )
    else:
        status = (
            f" TPS {_last_tps:5.1f}  │"
            f"  Reqs {_request_count}  │"
            f"  Total {_total_tokens} tok  │"
            f"  ↑{up_str}"
        )
    # Pad to fill width and avoid leftover chars
    status = status.ljust(78)
    # Save cursor -> go to line 2 col 1 -> print -> restore cursor
    sys.stdout.write(f"\033[s\033[2;1H\033[36m{status}\033[0m\033[u")
    sys.stdout.flush()

async def telemetry_loop():
    """Background task: updates the fixed top status bar every 2 seconds."""
    await asyncio.sleep(2)
    while True:
        try:
            _update_header()
        except:
            pass
        await asyncio.sleep(2)

# ── Shared HTTP Session ────────────────────────────────────
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=300, connect=10)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session

async def cleanup_session(app):
    if _session and not _session.closed:
        await _session.close()

# ── Proxy Handler ──────────────────────────────────────────
_last_model_check = 0
_generating = False  # True while streaming tokens

# ANSI helpers
C_DIM    = "\033[90m"
C_CYAN   = "\033[36m"
C_GREEN  = "\033[32m"
C_YELLOW = "\033[33m"
C_RED    = "\033[31m"
C_BOLD   = "\033[1m"
C_RESET  = "\033[0m"

def _detect_client(headers):
    """Identify the calling IDE/tool from User-Agent."""
    ua = headers.get("User-Agent", "").lower()
    if "jetbrains" in ua or "phpstorm" in ua or "intellij" in ua or "webstorm" in ua:
        for name in ["PhpStorm", "IntelliJ", "WebStorm", "PyCharm", "Rider", "GoLand", "CLion"]:
            if name.lower() in ua:
                return name
        return "JetBrains IDE"
    elif "vscode" in ua or "visual studio code" in ua:
        return "VS Code"
    elif "cursor" in ua:
        return "Cursor"
    elif "continue" in ua:
        return "Continue"
    elif "copilot" in ua:
        return "Copilot"
    elif "python" in ua:
        return "Python"
    elif "curl" in ua:
        return "curl"
    return None

def _extract_prompt_preview(body_bytes):
    """Get a short preview of what the user is asking."""
    try:
        data = json.loads(body_bytes)
        messages = data.get("messages", [])
        # Get last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):  # multi-modal
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            content = part.get("text", "")
                            break
                    else:
                        content = ""
                content = content.strip().replace("\n", " ")
                if len(content) > 60:
                    return content[:57] + "..."
                return content
        # FIM / plain completion
        prompt = data.get("prompt", "")
        if prompt:
            prompt = prompt.strip().replace("\n", " ")
            if len(prompt) > 60:
                return prompt[:57] + "..."
            return prompt
    except:
        pass
    return None

def _progress_line(tokens, elapsed):
    """Build an in-place progress update line."""
    tps = tokens / elapsed if elapsed > 0 else 0
    bar_len = min(tokens // 3, 20)  # ~3 tokens per block, max 20
    bar = "█" * bar_len + "░" * (20 - bar_len)
    return f"  {C_DIM}       {bar}  {tokens} tokens  ({elapsed:.1f}s, {tps:.1f} tok/s){C_RESET}"

async def handle_proxy(request):
    global _request_count, _last_model_check, _generating, _completion_id, _total_tokens
    target_path = request.path
    if request.query_string:
        target_path += "?" + request.query_string
    url = f"{TARGET_URL}{target_path}"
    body = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}

    is_completion = "completions" in target_path
    is_chat = "chat/completions" in target_path
    if is_completion:
        reset_tokens()

    # Extract context for logging
    req_model = None
    prompt_preview = None
    client = _detect_client(request.headers)
    if body and is_completion:
        try:
            req_json = json.loads(body)
            req_model = req_json.get("model", "?")
        except: pass
        prompt_preview = _extract_prompt_preview(body)

    _request_count += 1
    req_start = time.time()
    this_id = None

    # Log arrival for completions
    if is_completion:
        _completion_id += 1
        this_id = _completion_id
        src = f" via {C_CYAN}{client}{C_RESET}" if client else ""
        kind = "Chat" if is_chat else "Completion"
        model_str = f"{C_BOLD}{req_model or '?'}{C_RESET}"
        tag = f"{C_DIM}#{this_id}{C_RESET}"
        log(f"{'─' * 60}")
        log(f"▶  {tag}  {kind} request{src}")
        log(f"   Model: {model_str}")
        if prompt_preview:
            log(f"   {C_DIM}\"{prompt_preview}\"{C_RESET}")
        _generating = True

    session = await get_session()
    try:
        async with session.request(request.method, url, headers=headers, data=body) as response:
            client_response = web.StreamResponse(status=response.status, reason=response.reason)
            for k, v in response.headers.items():
                if k.lower() not in ['transfer-encoding', 'content-length']:
                    client_response.headers[k] = v

            is_sse = 'text/event-stream' in response.headers.get('Content-Type', '')
            request_id = f"chatcmpl-{uuid.uuid4()}"
            await client_response.prepare(request)

            if is_sse:
                buffer = ""
                last_progress = 0
                async for chunk in response.content:
                    if chunk:
                        buffer += chunk.decode('utf-8', errors='replace')
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            try:
                                if line.startswith('data: ') and line != 'data: [DONE]':
                                    data = json.loads(line[6:])
                                    if 'id' not in data: data['id'] = request_id
                                    # Strip unsupported fields
                                    for ch in data.get('choices', []):
                                        ch.get('delta', {}).pop('reasoning_content', None)
                                    # Each SSE event must end with a blank line for strict clients.
                                    await client_response.write(f"data: {json.dumps(data)}\n\n".encode('utf-8'))
                                    if is_completion:
                                        record_token()
                                        # Update progress every 10 tokens
                                        if _token_count - last_progress >= 10:
                                            elapsed = time.time() - req_start
                                            sys.stdout.write(f"\r{_progress_line(_token_count, elapsed)}")
                                            sys.stdout.flush()
                                            last_progress = _token_count
                                else:
                                    await client_response.write((line + '\n').encode('utf-8'))
                            except:
                                await client_response.write((line + '\n').encode('utf-8'))
                if buffer.strip():
                    await client_response.write(buffer.encode('utf-8'))
            else:
                async for chunk in response.content:
                    await client_response.write(chunk)

            # Final logging
            elapsed = time.time() - req_start
            if is_completion:
                # Clear progress line and print final summary
                sys.stdout.write(f"\r{' ' * 80}\r")
                sys.stdout.flush()
                tps = _token_count / elapsed if elapsed > 0 else 0
                _total_tokens += _token_count
                tag = f"{C_DIM}#{this_id}{C_RESET}" if this_id else ""
                log(f"{C_GREEN}✓{C_RESET}  {tag}  {C_BOLD}{_token_count}{C_RESET} tokens  │  {elapsed:.1f}s  │  {C_CYAN}{tps:.1f} tok/s{C_RESET}")
                _generating = False
            else:
                _log_non_completion(target_path, response.status, elapsed)

            return client_response
    except asyncio.TimeoutError:
        _generating = False
        sys.stdout.write(f"\r{' ' * 80}\r")
        log(f"{C_YELLOW}⚠  Timeout{C_RESET} - server did not respond within 300s")
        return web.Response(text="Proxy Error: Upstream request timed out (300s)", status=504)
    except aiohttp.ClientConnectorError:
        _generating = False
        log(f"{C_RED}✗  Connection failed{C_RESET} - cannot reach {TARGET_URL}")
        log(f"   {C_DIM}Is OVMS running? Try: .\\start_server.ps1{C_RESET}")
        return web.Response(text=f"Proxy Error: Cannot connect to {TARGET_URL}", status=502)
    except Exception as e:
        _generating = False
        log(f"{C_RED}✗  Error:{C_RESET} {e}")
        return web.Response(text=f"Proxy Error: {str(e)}", status=500)

def _log_non_completion(path, status, elapsed):
    global _last_model_check
    now = time.time()
    p = path.lower()

    if "/models" in p:
        if now - _last_model_check > 30:
            log(f"{C_DIM}🔍  Model list checked ({elapsed:.1f}s){C_RESET}")
            _last_model_check = now
    elif status >= 400:
        log(f"{C_YELLOW}⚠  {path} → {status}{C_RESET} ({elapsed:.1f}s)")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C_DIM}{ts}{C_RESET}  {msg}", flush=True)

# ── App Setup ──────────────────────────────────────────────
app = web.Application()
app.on_cleanup.append(cleanup_session)
app.router.add_route('*', '/{path_info:.*}', handle_proxy)

async def start_telemetry(app):
    app['telemetry_task'] = asyncio.create_task(telemetry_loop())

async def stop_telemetry(app):
    app['telemetry_task'].cancel()
    try: await app['telemetry_task']
    except asyncio.CancelledError: pass

app.on_startup.append(start_telemetry)
app.on_cleanup.append(stop_telemetry)

if __name__ == '__main__':
    # Set up fixed top bar (3 lines) + scrolling log region below
    title = f" Proxy :{PORT} -> {TARGET_URL}"
    if _has_xpu:
        title += "  │  xpu-smi: ✓"
    else:
        title += "  │  xpu-smi: ✗"

    # Clear screen, print header
    sys.stdout.write("\033[2J\033[H")                  # clear + home
    sys.stdout.write(f"\033[44;97m{title.ljust(78)}\033[0m\n")  # line 1: title (white on blue)
    sys.stdout.write(f"\033[36m{' ' * 78}\033[0m\n")           # line 2: metrics placeholder
    sys.stdout.write(f"{'─' * 78}\n")                          # line 3: separator
    # Set scroll region to lines 4+
    sys.stdout.write("\033[4;r")
    # Move cursor to line 4
    sys.stdout.write("\033[4;1H")
    sys.stdout.flush()

    print("  Ready. Waiting for requests...\n", flush=True)
    web.run_app(app, port=PORT, access_log=None, print=lambda *a: None)
