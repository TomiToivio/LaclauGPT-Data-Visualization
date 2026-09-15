"""Command-line launcher and deployment diagnostics for Visualization."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import get_settings
from .service import readiness, streamlit_command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laclaugpt-visualize")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve", "health", "profile"),
        default="serve",
        help="serve dashboard (default), validate readiness, or print non-secret profile",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    settings.ensure_local_directories()

    if args.command == "profile":
        print(json.dumps(settings.safe_summary(), indent=2, default=str))
        return 0
    if args.command == "health":
        result = readiness(settings)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["status"] == "ready" else 1

    command = streamlit_command(settings)
    command[0] = sys.executable
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
