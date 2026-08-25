from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.core.config import RuntimeConfig, load_core_config
from tools.core.downloader import pull_model
from tools.core.lifecycle import OvmsLifecycleService
from tools.core.manifest import discover_all_models
from tools.core.process_manager import ProcessManager, ProcessState
from tools.core.readiness import probe_gateway_readiness, probe_ovms_readiness, wait_for_ovms_ready


def _format_output(data: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    print(f"{k}: {json.dumps(v, default=str)}")
                else:
                    print(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(item)
        else:
            print(str(data))


def cmd_status(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    service = OvmsLifecycleService(cfg)
    st = service.status()
    models = discover_all_models(cfg)
    pm = ProcessManager(cfg)

    ovms_proc_state = pm.get_status("ovms")
    gw_proc_state = pm.get_status("gateway")
    gw_ready = probe_gateway_readiness(cfg.proxy_port, client_host=cfg.client_host)

    downloaded = [name for name, info in models.items() if info.is_downloaded]

    status_data = {
        "ovms": {
            "reachable": st.get("reachable", False),
            "rest_port": cfg.ovms_port,
            "grpc_port": cfg.ovms_grpc_port,
            "process_state": ovms_proc_state.value,
            "loaded_models": st.get("loaded_models", []),
            "configured_model": st.get("configured_model"),
        },
        "gateway": {
            "reachable": gw_ready,
            "port": cfg.proxy_port,
            "bind_host": cfg.proxy_bind_host,
            "client_host": cfg.client_host,
            "process_state": gw_proc_state.value,
        },
        "models": {
            "active_model": st.get("configured_model") or (st.get("loaded_models")[0] if st.get("loaded_models") else None),
            "installed_count": len(downloaded),
            "installed_models": downloaded,
            "total_registered": len(models),
        },
    }

    if args.json:
        _format_output(status_data, as_json=True)
    else:
        print("=" * 60)
        print("🖥️  INTEL ARC AI STUDIO - RUNTIME STATUS")
        print("=" * 60)
        print(f"• OVMS Service:       {'🟢 ONLINE' if status_data['ovms']['reachable'] else '🔴 OFFLINE'} (Port {cfg.ovms_port}, State: {ovms_proc_state.value})")
        print(f"• Gateway Proxy:      {'🟢 ONLINE' if status_data['gateway']['reachable'] else '⚪ STANDBY'} (Port {cfg.proxy_port}, State: {gw_proc_state.value})")
        print(f"• Active Model:       {status_data['models']['active_model'] or 'None'}")
        print(f"• In-Memory Models:   {', '.join(status_data['ovms']['loaded_models']) or 'None'}")
        print(f"• Installed on Disk:  {len(downloaded)} / {len(models)} models ready")
        print("=" * 60)

    return 0


def cmd_list(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    models = discover_all_models(cfg)
    service = OvmsLifecycleService(cfg)
    st = service.status()
    active = st.get("configured_model")
    loaded = set(st.get("loaded_models", []))

    result = []
    for name, info in models.items():
        is_active = (name == active)
        is_loaded = (name in loaded)
        result.append({
            "name": name,
            "repo_id": info.repo_id,
            "path": info.local_path,
            "downloaded": info.is_downloaded,
            "active": is_active,
            "loaded": is_loaded,
            "device": info.catalog_entry.device if info.catalog_entry else "GPU",
            "description": info.description,
        })

    if args.json:
        _format_output({"models": result}, as_json=True)
    else:
        print(f"{'STATUS':<16} {'MODEL NAME':<30} {'LOCAL PATH'}")
        print("-" * 80)
        for m in result:
            if m["loaded"]:
                badge = "[LOADED]"
            elif m["active"]:
                badge = "[ACTIVE]"
            elif m["downloaded"]:
                badge = "[READY]"
            else:
                badge = "[NOT DOWNLOADED]"
            print(f"{badge:<16} {m['name']:<30} {m['path']}")

    return 0


def cmd_switch(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    service = OvmsLifecycleService(cfg)
    target_model = args.model_name or getattr(args, "name", None)
    if not target_model:
        if args.json:
            _format_output({"error": "switch command requires a model name argument.", "status": "failed"}, as_json=True)
        else:
            print("❌ switch command requires a model name argument.", file=sys.stderr)
        return 1

    try:
        res = service.switch_model(
            model_name=target_model,
            model_path=args.path,
            timeout_sec=args.timeout,
            no_wait=args.no_wait,
            dry_run=args.dry_run,
        )
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Switch failed: {exc}", file=sys.stderr)
        return 1


def cmd_configure(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    target_model = args.model_name or getattr(args, "name", None)
    if not target_model:
        if args.json:
            _format_output({"error": "configure command requires a model name.", "status": "failed"}, as_json=True)
        else:
            print("❌ configure command requires a model name.", file=sys.stderr)
        return 1

    service = OvmsLifecycleService(cfg)
    try:
        res = service.enable_model(
            model_name=target_model,
            model_path=args.path,
            dry_run=args.dry_run,
            no_reload=args.no_reload,
        )
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Configure failed: {exc}", file=sys.stderr)
        return 1


def cmd_enable(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    target_model = args.model_name or getattr(args, "name", None)
    if not target_model:
        if args.json:
            _format_output({"error": "enable command requires a model name argument.", "status": "failed"}, as_json=True)
        else:
            print("❌ enable command requires a model name argument.", file=sys.stderr)
        return 1

    service = OvmsLifecycleService(cfg)
    try:
        res = service.enable_model(
            model_name=target_model,
            model_path=args.path,
            dry_run=args.dry_run,
            no_reload=args.no_reload,
        )
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Enable failed: {exc}", file=sys.stderr)
        return 1


def cmd_disable(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    target_model = args.model_name or getattr(args, "name", None)
    if not target_model:
        if args.json:
            _format_output({"error": "disable command requires a model name argument.", "status": "failed"}, as_json=True)
        else:
            print("❌ disable command requires a model name argument.", file=sys.stderr)
        return 1

    service = OvmsLifecycleService(cfg)
    try:
        res = service.disable_model(
            model_name=target_model,
            dry_run=args.dry_run,
            no_reload=args.no_reload,
        )
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Disable failed: {exc}", file=sys.stderr)
        return 1


def cmd_pull(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    target_model = args.model_name or getattr(args, "name", None)
    if not target_model:
        if args.json:
            _format_output({"error": "pull command requires a model name argument.", "status": "failed"}, as_json=True)
        else:
            print("❌ pull command requires a model name argument.", file=sys.stderr)
        return 1

    dest_val = getattr(args, "dest", None) or getattr(args, "path", None)
    dest = Path(dest_val) if dest_val else None

    def log(msg: str) -> None:
        if not args.json:
            print(f"⏳ {msg}")

    try:
        dest_dir = pull_model(
            config=cfg,
            model_name=target_model,
            on_progress=log,
            destination_override=dest,
        )
        if args.json:
            _format_output({
                "status": "success",
                "model": target_model,
                "destination": str(dest_dir),
            }, as_json=True)
        else:
            print(f"✅ Successfully pulled and verified model '{target_model}' at: {dest_dir}")
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Pull failed: {exc}", file=sys.stderr)
        return 1


def cmd_reload(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    service = OvmsLifecycleService(cfg)
    timeout = getattr(args, "timeout", 30)
    try:
        res = service.reload(timeout_sec=timeout)
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Reload failed: {exc}", file=sys.stderr)
        return 1


def cmd_rollback(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    service = OvmsLifecycleService(cfg)
    target = getattr(args, "target", None)
    try:
        res = service.rollback(target_backup=target)
        _format_output(res, as_json=args.json)
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"error": str(exc), "status": "failed"}, as_json=True)
        else:
            print(f"❌ Rollback failed: {exc}", file=sys.stderr)
        return 1


def cmd_test_ready(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    port = args.port or cfg.ovms_port
    timeout = args.timeout or 30
    model = args.model

    if not args.json:
        print(f"Checking OVMS readiness on port {port} (timeout: {timeout}s)...")

    ready = wait_for_ovms_ready(
        rest_port=port,
        client_host=cfg.client_host,
        timeout_sec=timeout,
        expected_model=model,
    )

    status_res = probe_ovms_readiness(rest_port=port, client_host=cfg.client_host)

    if args.json:
        _format_output({
            "ready": ready,
            "reachable": status_res.reachable,
            "models": status_res.models,
            "error": status_res.error,
        }, as_json=True)
    else:
        if ready:
            print(f"✅ OVMS is READY on port {port}. Models: {status_res.models}")
        else:
            print(f"❌ OVMS is NOT ready on port {port}. Error: {status_res.error}", file=sys.stderr)

    return 0 if ready else 1


def cmd_start(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    pm = ProcessManager(cfg)
    comp = args.component.lower()
    try:
        if comp == "ovms":
            state = pm.start_ovms(wait_for_ready=args.wait, timeout_sec=args.timeout)
        elif comp in {"gateway", "proxy"}:
            state = pm.start_gateway(wait_for_ready=args.wait, timeout_sec=args.timeout)
        else:
            print(f"❌ Unknown component: {comp}. Must be 'ovms' or 'gateway'.", file=sys.stderr)
            return 1

        if args.json:
            _format_output({"component": comp, "state": state.value}, as_json=True)
        else:
            print(f"✅ Started {comp.upper()} -> {state.value}")
        return 0
    except Exception as exc:
        if args.json:
            _format_output({"component": comp, "error": str(exc)}, as_json=True)
        else:
            print(f"❌ Could not start {comp}: {exc}", file=sys.stderr)
        return 1


def cmd_stop(cfg: RuntimeConfig, args: argparse.Namespace) -> int:
    pm = ProcessManager(cfg)
    comp = args.component.lower()
    comp_name = "gateway" if comp == "proxy" else comp
    stopped = pm.stop_component(comp_name)
    if args.json:
        _format_output({"component": comp, "stopped": stopped}, as_json=True)
    else:
        if stopped:
            print(f"✅ Stopped owned {comp.upper()} process.")
        else:
            print(f"ℹ️ No owned running process found for {comp.upper()}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.core.cli",
        description="Intel Arc OVMS Studio - Core Management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Get runtime status")
    p_status.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # list & native-list
    for list_cmd in ["list", "native-list"]:
        p_list = subparsers.add_parser(list_cmd, help="List registered and installed models")
        p_list.add_argument("--repository-path", default=None, help="Optional model repository path")
        p_list.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # switch
    p_switch = subparsers.add_parser("switch", help="Hot-swap the active OVMS model")
    p_switch.add_argument("model_name", nargs="?", default=None, help="Model name to switch to")
    p_switch.add_argument("--name", default=None, help="Model name alias")
    p_switch.add_argument("--path", default=None, help="Optional custom model path")
    p_switch.add_argument("--timeout", type=int, default=120, help="Wait timeout in seconds")
    p_switch.add_argument("--no-wait", action="store_true", help="Do not wait for OVMS reload to complete")
    p_switch.add_argument("--dry-run", action="store_true", help="Simulate switch without mutating config")
    p_switch.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # configure
    p_configure = subparsers.add_parser("configure", help="Configure a model in config.json")
    p_configure.add_argument("model_name", nargs="?", default=None, help="Model name to configure")
    p_configure.add_argument("--name", default=None, help="Model name alias")
    p_configure.add_argument("--path", default=None, help="Model directory path")
    p_configure.add_argument("--task", default="text_generation", help="Model task type")
    p_configure.add_argument("--device", default="GPU", help="Target accelerator device")
    p_configure.add_argument("--performance-profile", default="Balanced", help="Performance profile")
    p_configure.add_argument("--repository-path", default=None, help="Optional repository path")
    p_configure.add_argument("--config-path", default=None, help="Optional config path")
    p_configure.add_argument("--no-reload", action="store_true", help="Do not reload OVMS after updating config")
    p_configure.add_argument("--dry-run", action="store_true", help="Simulate without mutating config")
    p_configure.add_argument("--json", action="store_true", help="Output JSON")

    # enable
    p_enable = subparsers.add_parser("enable", help="Enable a model in config.json")
    p_enable.add_argument("model_name", nargs="?", default=None, help="Model name to enable")
    p_enable.add_argument("--name", default=None, help="Model name alias")
    p_enable.add_argument("--path", default=None, help="Optional model directory path")
    p_enable.add_argument("--config-path", default=None, help="Optional config path")
    p_enable.add_argument("--no-reload", action="store_true", help="Do not reload OVMS after updating config")
    p_enable.add_argument("--dry-run", action="store_true", help="Simulate without mutating config")
    p_enable.add_argument("--json", action="store_true", help="Output JSON")

    # disable
    p_disable = subparsers.add_parser("disable", help="Disable a model in config.json")
    p_disable.add_argument("model_name", nargs="?", default=None, help="Model name to disable")
    p_disable.add_argument("--name", default=None, help="Model name alias")
    p_disable.add_argument("--config-path", default=None, help="Optional config path")
    p_disable.add_argument("--no-reload", action="store_true", help="Do not reload OVMS after updating config")
    p_disable.add_argument("--dry-run", action="store_true", help="Simulate without mutating config")
    p_disable.add_argument("--json", action="store_true", help="Output JSON")

    # pull
    p_pull = subparsers.add_parser("pull", help="Download and verify an OpenVINO model")
    p_pull.add_argument("model_name", nargs="?", default=None, help="Model name to pull")
    p_pull.add_argument("--name", default=None, help="Model name alias")
    p_pull.add_argument("--dest", default=None, help="Destination directory path")
    p_pull.add_argument("--path", default=None, help="Destination directory path alias")
    p_pull.add_argument("--repository-path", default=None, help="Optional model repository path")
    p_pull.add_argument("--task", default="text_generation", help="Model task type")
    p_pull.add_argument("--device", default="GPU", help="Target accelerator device")
    p_pull.add_argument("--performance-profile", default="Balanced", help="Performance profile")
    p_pull.add_argument("--gguf-filename", default=None, help="Optional GGUF filename")
    p_pull.add_argument("--overwrite", action="store_true", help="Overwrite existing model files")
    p_pull.add_argument("--json", action="store_true", help="Output JSON")

    # reload
    p_reload = subparsers.add_parser("reload", help="Trigger OVMS config reload")
    p_reload.add_argument("--config-path", default=None, help="Optional config path")
    p_reload.add_argument("--timeout", type=int, default=30, help="Wait timeout")
    p_reload.add_argument("--json", action="store_true", help="Output JSON")

    # rollback
    p_rollback = subparsers.add_parser("rollback", help="Roll back config.json to last backup")
    p_rollback.add_argument("--config-path", default=None, help="Optional config path")
    p_rollback.add_argument("--target", default=None, help="Optional target backup path")
    p_rollback.add_argument("--json", action="store_true", help="Output JSON")

    # test-ready
    p_ready = subparsers.add_parser("test-ready", help="Test OVMS readiness")
    p_ready.add_argument("--port", type=int, default=None, help="OVMS REST port")
    p_ready.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    p_ready.add_argument("--model", default=None, help="Expected loaded model name")
    p_ready.add_argument("--json", action="store_true", help="Output JSON")

    # start
    p_start = subparsers.add_parser("start", help="Start runtime component (ovms|gateway)")
    p_start.add_argument("component", choices=["ovms", "gateway", "proxy"], help="Component to start")
    p_start.add_argument("--wait", action="store_true", default=True, help="Wait for readiness")
    p_start.add_argument("--timeout", type=int, default=60, help="Startup timeout in seconds")
    p_start.add_argument("--json", action="store_true", help="Output JSON")

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop runtime component (ovms|gateway)")
    p_stop.add_argument("component", choices=["ovms", "gateway", "proxy"], help="Component to stop")
    p_stop.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = load_core_config()

    handlers = {
        "status": cmd_status,
        "list": cmd_list,
        "native-list": cmd_list,
        "switch": cmd_switch,
        "configure": cmd_configure,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "pull": cmd_pull,
        "reload": cmd_reload,
        "rollback": cmd_rollback,
        "test-ready": cmd_test_ready,
        "start": cmd_start,
        "stop": cmd_stop,
    }

    handler = handlers.get(args.command)
    if not handler:
        print(f"❌ Unknown command: {args.command}", file=sys.stderr)
        return 1

    return handler(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
