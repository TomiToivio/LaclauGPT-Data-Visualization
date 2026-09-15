"""Command-line launcher for the visualization dashboard."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import get_settings


def main() -> int:
    settings = get_settings()
    settings.ensure_local_directories()
    app = Path(__file__).with_name("app.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


if __name__ == "__main__":
    raise SystemExit(main())
