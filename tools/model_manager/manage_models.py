from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.model_manager.runtime_cli import load_runtime_settings, run_ovms_cli
from tools.model_manager.swap_service import SwapService, make_paths

def emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="OVMS model lifecycle manager.")
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status"); sub.add_parser("list")
    sw = sub.add_parser("switch"); sw.add_argument("model"); sw.add_argument("--path"); sw.add_argument("--timeout", type=int, default=180); sw.add_argument("--no-wait", action="store_true"); sw.add_argument("--dry-run", action="store_true")
    sub.add_parser("rollback")
    pull = sub.add_parser("pull"); pull.add_argument("source"); pull.add_argument("--name"); pull.add_argument("--task", default="text_generation"); pull.add_argument("--device", default="GPU"); pull.add_argument("--cache-size", type=int, default=2); pull.add_argument("--max-num-seqs", type=int, default=2)
    cfg = sub.add_parser("configure"); cfg.add_argument("path"); cfg.add_argument("--name"); cfg.add_argument("--task", default="text_generation"); cfg.add_argument("--device", default="GPU"); cfg.add_argument("--cache-size", type=int, default=2); cfg.add_argument("--max-num-seqs", type=int, default=2)
    en = sub.add_parser("enable"); en.add_argument("model"); en.add_argument("--path")
    dis = sub.add_parser("disable"); dis.add_argument("model")
    return p

def native(root: Path, args: list[str]) -> dict:
    result = run_ovms_cli(root, args)
    return {"command": args, "stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "returncode": result.returncode}

def main() -> int:
    args = build_parser().parse_args(); root = Path(args.root).resolve(); service = SwapService(make_paths(root))
    try:
        if args.cmd == "status": emit(service.status())
        elif args.cmd == "list": emit({"models": service.list_models()})
        elif args.cmd == "switch": emit(service.switch(args.model, args.path, args.timeout, args.no_wait, args.dry_run))
        elif args.cmd == "rollback": emit(service.rollback())
        elif args.cmd == "pull":
            rs = load_runtime_settings(root); name = args.name or args.source.split("/")[-1]
            emit(native(root, ["--pull", "--source_model", args.source, "--model_repository_path", str(rs.model_repository), "--model_name", name, "--target_device", args.device, "--task", args.task, "--cache_size", str(args.cache_size), "--max_num_seqs", str(args.max_num_seqs)]))
        elif args.cmd == "configure":
            cmd = ["--configure", "--model_path", str(Path(args.path).resolve()), "--task", args.task, "--target_device", args.device, "--cache_size", str(args.cache_size), "--max_num_seqs", str(args.max_num_seqs)]
            if args.name: cmd += ["--model_name", args.name]
            emit(native(root, cmd))
        elif args.cmd == "enable":
            rs = load_runtime_settings(root); cmd = ["--add_to_config", "--config_path", str(rs.config_path), "--model_name", args.model]
            if args.path: cmd += ["--model_path", args.path]
            emit(native(root, cmd))
        elif args.cmd == "disable":
            rs = load_runtime_settings(root); emit(native(root, ["--remove_from_config", "--config_path", str(rs.config_path), "--model_name", args.model]))
        return 0
    except Exception as exc:
        emit({"error": str(exc)}); return 1

if __name__ == "__main__": raise SystemExit(main())
