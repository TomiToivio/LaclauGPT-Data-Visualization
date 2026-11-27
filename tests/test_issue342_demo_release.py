"""A public demo copy must be installable and updatable by someone who does not own Laskin (#342).

These tests pin the operational half of the handover: the unit a public host installs, and the
release switch that makes a daily update either provably good or provably rolled back.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
UNIT = REPO_ROOT / "deploy" / "laclaugpt-visualization-public-demo.service.example"
UPDATER = REPO_ROOT / "scripts" / "update_ai26_demo_release.sh"
EXPORTER = REPO_ROOT / "scripts" / "export_ai26_demo_bundle.py"


def test_the_demo_unit_serves_the_bundle_and_nothing_else() -> None:
    unit = UNIT.read_text(encoding="utf-8")
    assert "LACLAUGPT_VIS_DEMO_MODE=true" in unit
    assert "LACLAUGPT_VIS_DEMO_BUNDLE=<demo-root>/current/records.jsonl" in unit
    # The copy must not be able to reach a private endpoint even by accident.
    for forbidden in ("MONGODB_URI", "REDIS_URL", "S3_ACCESS_KEY"):
        assert forbidden not in unit
    assert "--server.address 127.0.0.1" in unit
    assert "ProtectSystem=strict" in unit and "ReadOnlyPaths=" in unit


def test_the_updater_is_valid_bash_and_documents_rollback() -> None:
    source = UPDATER.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(UPDATER)], check=True)
    assert "sha256" in source and "manifest.json" in source
    assert "rolled back" in source
    assert "--dry-run" in source


def test_a_verified_bundle_passes_the_updater_dry_run(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    subprocess.run(
        [sys.executable, str(EXPORTER), "--output", str(bundle), "--synthetic"],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"], "the exporter must record per-file checksums"
    result = subprocess.run(
        [
            "bash",
            str(UPDATER),
            "--bundle",
            str(bundle),
            "--root",
            str(tmp_path / "demo-root"),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "verified 1 file(s)" in result.stdout
    assert "dry run: would write" in result.stdout
    assert not (tmp_path / "demo-root").exists(), "a dry run must not create the demo root"


def test_a_tampered_bundle_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    subprocess.run(
        [sys.executable, str(EXPORTER), "--output", str(bundle), "--synthetic"],
        check=True,
        capture_output=True,
        text=True,
    )
    records = bundle / "records.jsonl"
    records.write_text(records.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    result = subprocess.run(
        [
            "bash",
            str(UPDATER),
            "--bundle",
            str(bundle),
            "--root",
            str(tmp_path / "demo-root"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "checksum mismatch" in (result.stdout + result.stderr)
    assert not (tmp_path / "demo-root" / "current").exists()
