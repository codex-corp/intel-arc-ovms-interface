from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from tools.core.config import RuntimeConfig
from tools.core.env_resolver import resolve_ovms_environment
from tools.core.manifest import is_model_weights_ready, load_manifest
from tools.model_manager.model_registry import load_registry


GRAPH_PBTXT_TEMPLATE = """input_stream: "HTTP_REQUEST_PAYLOAD:input"
output_stream: "HTTP_RESPONSE_PAYLOAD:output"
node: {{
  name: "LLMExecutor"
  calculator: "HttpLLMCalculator"
  input_stream: "LOOPBACK:loopback"
  input_stream: "HTTP_REQUEST_PAYLOAD:input"
  input_side_packet: "LLM_NODE_RESOURCES:llm"
  output_stream: "LOOPBACK:loopback"
  output_stream: "HTTP_RESPONSE_PAYLOAD:output"
  input_stream_info: {{ tag_index: 'LOOPBACK:0', back_edge: true }}
  node_options: {{
    [type.googleapis.com / mediapipe.LLMCalculatorOptions]: {{
      models_path: "./"
      cache_size: 1
      device: "{device}"
      enable_prefix_caching: true
      max_num_seqs: 1
      plugin_config: "{{\\"KV_CACHE_PRECISION\\": \\"u8\\"}}"
    }}
  }}
  input_stream_handler {{
    input_stream_handler: "SyncSetInputStreamHandler",
    options {{ [mediapipe.SyncSetInputStreamHandlerOptions.ext] {{ sync_set {{ tag_index: "LOOPBACK:0" }} }} }}
  }}
}}
"""


def fallback_legacy_graph_pbtxt_if_missing(dest_dir: Path, device: str = "GPU") -> bool:
    """
    Compatibility fallback: Only invoked if native OVMS or upstream source did not produce
    graph.pbtxt. Never overwrites an existing configuration.
    """
    graph_file = dest_dir / "graph.pbtxt"
    if not graph_file.exists():
        content = GRAPH_PBTXT_TEMPLATE.format(device=device)
        graph_file.write_text(content, encoding="utf-8")
        return True
    return False


def _get_dir_size_mb(path: Path) -> float:
    """Calculates total size of all files in directory in megabytes."""
    try:
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
            return total / (1024 * 1024)
        return total / (1024 * 1024)
    except Exception:
        return 0.0


def pull_model(
    config: RuntimeConfig,
    model_name: str,
    on_progress: Optional[Callable[[str], None]] = None,
    destination_override: Optional[Path] = None,
) -> Path:
    """
    Downloads and prepares an OpenVINO model.
    Primary: Native ovms.exe --pull engine.
    Fallback: Hugging Face hub snapshot_download with live size monitoring.
    """
    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    catalog = load_manifest(config.manifest_path)
    entry = catalog.get(model_name)
    repo_id = entry.repo_id if entry else model_name

    # Determine destination folder
    if destination_override:
        dest_dir = Path(destination_override).resolve()
    else:
        registry = load_registry(config.legacy_registry_path) if config.legacy_registry_path.exists() else {}
        dest_path = registry.get(model_name)
        if not dest_path:
            dest_path = str(config.root / "models" / model_name)
        dest_dir = Path(dest_path).resolve()

    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f"Connecting to repository for '{model_name}' ({repo_id})...")

    # 1. Primary: Native OVMS Pull (ovms.exe --pull is authoritative)
    ovms_exe = config.ovms_dir / "ovms.exe"
    native_success = False

    if ovms_exe.exists():
        log("Executing native OVMS pull engine (ovms.exe --pull)...")
        env = resolve_ovms_environment(config.ovms_dir)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        cmd = [
            str(ovms_exe),
            "--pull",
            repo_id,
            "--model_repository_path",
            str(dest_dir.parent),
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(config.root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                bufsize=1,
            )

            if proc.stdout:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if line:
                        log(f"[OVMS] {line}")

            proc.wait(timeout=600)
            if proc.returncode == 0 and is_model_weights_ready(str(dest_dir)):
                native_success = True
                log("Native OVMS pull completed successfully.")
        except Exception as exc:
            log(f"Native pull encountered: {exc}. Proceeding with downloader fallback...")

    # 2. Fallback: Direct Hub Downloader with Live Progress Tracking
    if not native_success and not is_model_weights_ready(str(dest_dir)):
        log(f"Downloading OpenVINO INT4 weights from Hugging Face ({repo_id})...")
        stop_event = threading.Event()

        def monitor_progress():
            while not stop_event.wait(1.5):
                size_mb = _get_dir_size_mb(dest_dir)
                if size_mb > 0:
                    if size_mb >= 1024:
                        log(f"Downloading model files: {size_mb / 1024:.2f} GB received...")
                    else:
                        log(f"Downloading model files: {size_mb:.1f} MB received...")

        monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
        monitor_thread.start()

        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=repo_id,
                local_dir=str(dest_dir),
            )
        except Exception as exc:
            raise RuntimeError(f"Model download failed for '{model_name}' ({repo_id}): {exc}") from exc
        finally:
            stop_event.set()
            monitor_thread.join(timeout=1.0)

        final_mb = _get_dir_size_mb(dest_dir)
        log(f"Download complete ({final_mb / 1024:.2f} GB). Verifying weights integrity...")

        # Compatibility fallback: if native OVMS was not used and graph.pbtxt is missing, generate fallback
        if not (dest_dir / "graph.pbtxt").exists():
            device = entry.device if entry else "GPU"
            fallback_legacy_graph_pbtxt_if_missing(dest_dir, device=device)

    # 3. Weights Verification
    if not is_model_weights_ready(str(dest_dir)):
        raise RuntimeError(
            f"Download finished for '{model_name}', but required binary weights (.bin/.gguf) were not found in {dest_dir}."
        )

    # 4. Update legacy registry for backward compatibility
    try:
        reg_path = config.legacy_registry_path
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        current_reg = load_registry(reg_path) if reg_path.exists() else {}
        current_reg[model_name] = str(dest_dir)
        temp_file = reg_path.with_suffix(reg_path.suffix + ".tmp")
        temp_file.write_text(json.dumps({"models": current_reg}, indent=2), encoding="utf-8")
        temp_file.replace(reg_path)
    except Exception:
        pass

    log(f"Model '{model_name}' successfully verified and registered in local storage!")
    return dest_dir
