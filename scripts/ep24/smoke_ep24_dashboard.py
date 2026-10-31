"""Real-server smoke test for the EP24 dashboard (#215).

Drives the deployed app with Streamlit's own AppTest harness against the actual export, and checks the
numbers it shows against MANIFEST.json. Run with the service's environment:

    LACLAUGPT_VIS_ANALYSIS_DATA_DIR=<export dir> python scripts/ep24/smoke_ep24_dashboard.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "laclaugpt_visualization" / "ep24_reprocessed_app.py"
data_dir = Path(os.environ["LACLAUGPT_VIS_ANALYSIS_DATA_DIR"])

from streamlit.testing.v1 import AppTest  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  — ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


manifest = json.loads((data_dir / "MANIFEST.json").read_text())
expected = {k: int(v["records"]) for k, v in manifest["countries"].items()}
total = int(manifest["records"])

app = AppTest.from_file(str(APP), default_timeout=180)
app.run()

check("the app starts without an exception", not app.exception, str(app.exception))
check("the title is the EP24 explorer",
      bool(app.title) and "EP24" in app.title[0].value, str(app.title[0].value if app.title else "none"))

body = " ".join(str(m.value) for m in app.markdown)
check("the export manifest is loaded", "Loaded export" in " ".join(
    str(c.value) for c in app.caption), "no manifest caption")

radios = app.sidebar.radio
check("the country selector exists", len(radios) >= 1)
options = list(radios[0].options) if radios else []
check("all countries are offered", len(options) == 4, str(options))
for country, count in expected.items():
    check(f"{country} scope shows {count}",
          any(o.lower().startswith(country) and f"({count})" in o for o in options),
          str(options))

sidebar_text = " ".join(str(m.value) for m in app.sidebar.markdown) + " ".join(
    str(c.value) for c in app.sidebar.caption)
check(f"the corpus total is {total}", str(total) in sidebar_text, sidebar_text[:200])

# Each country scope must render, not just appear in a list.
for country in expected:
    scope = next((o for o in options if o.lower().startswith(country)), None)
    if scope is None:
        continue
    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    at.sidebar.radio[0].set_value(scope).run()
    check(f"{country} scope renders without an exception", not at.exception, str(at.exception))

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print(f"OK: EP24 dashboard served {total} records "
      f"({', '.join(f'{k} {v}' for k, v in expected.items())}) from {data_dir.name}")
