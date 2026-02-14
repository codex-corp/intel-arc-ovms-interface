from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.model_manager.swap_service import SwapService, make_paths


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Local model manager for OVMS hot-swap flow.")
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[2]), help="Project root path.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show configured model and OVMS readiness.")
    sub.add_parser("list", help="List known models from registry.")

    sw = sub.add_parser("switch", help="Switch model in config.json/config.env and wait for OVMS readiness.")
    sw.add_argument("model", help="Target model id/name.")
    sw.add_argument("--path", help="Optional explicit model path.")
    sw.add_argument("--timeout", type=int, default=180, help="Readiness wait timeout in seconds.")
    sw.add_argument("--no-wait", action="store_true", help="Apply config without waiting for OVMS readiness.")
    sw.add_argument("--dry-run", action="store_true", help="Preview changes without writing files.")

    sub.add_parser("rollback", help="Restore last config.json backup.")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    service = SwapService(make_paths(root))

    try:
        if args.cmd == "status":
            _print_json(service.status())
            return 0

        if args.cmd == "list":
            _print_json({"models": service.list_models()})
            return 0

        if args.cmd == "switch":
            _print_json(
                service.switch(
                    model_name=args.model,
                    model_path=args.path,
                    timeout_sec=args.timeout,
                    no_wait=args.no_wait,
                    dry_run=args.dry_run,
                )
            )
            return 0

        if args.cmd == "rollback":
            _print_json(service.rollback())
            return 0

        parser.error("Unknown command")
        return 2
    except Exception as exc:
        _print_json({"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
