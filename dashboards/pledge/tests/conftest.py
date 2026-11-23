"""Make ``pledge_entities`` importable for this app's tests.

The dashboard is deployed as flat files (Streamlit runs it as a script, not a package module), so
the modules sit beside it rather than under ``src/``. Without this, a plain ``pytest`` from the repo
root collects these tests and fails on import.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
