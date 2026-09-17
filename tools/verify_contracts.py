#!/usr/bin/env python3
"""Offline contract-conformance check for the Visualization module.

Visualization is the last stage of the shared pipeline: it reads canonical
analysis records and renders researcher-facing views. It must do so through the
generic canonical adapter, without a project-specific one, and it must never
invent research identity or promote provisional interpretation.

This tool verifies, without network access, a live service or any research data:

* ``docs/CANONICAL_DATA_CONTRACT.md`` — ``source_url`` is the semantic identity
  and must reach the view model unchanged; backend ids and DataFrame row numbers
  are never research identity;
* the shared cross-module parity fixture — the versioned schema-drift tripwire
  vendored at ``tests/fixtures/canonical_parity_v1.json``;
* the visualization responsibility boundary — render generically, preserve
  provenance/uncertainty/review state, and keep review human-controlled.

The check is observational: it loads, transforms and compares. It never writes
research data, contacts a service or mutates configuration. Exit status is 0
when every check passes and 1 otherwise, so it can gate CI directly.

Usage::

    python tools/verify_contracts.py
    python tools/verify_contracts.py --fixture /path/to/canonical_parity_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC = REPOSITORY_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "canonical_parity_v1.json"

# Normative invariants from the fixture README.
EXPECTED_SOURCE_URL = "https://example.invalid/laclaugpt/synthetic/record-001"
EXPECTED_LEGACY_ID = "legacy-001"
EXPECTED_LEGACY_FIELD = "must-survive-roundtrip"


class CheckFailure(Exception):
    """A contract invariant was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def _load_fixture(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"parity fixture not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "parity fixture must be a JSON object")
    return payload


def _load_frame(path: Path) -> Any:
    from laclaugpt_visualization.data import load_frame

    frame = load_frame(path)
    _require(len(frame) == 1, f"the fixture must render exactly one row, got {len(frame)}")
    return frame


def check_generic_render(frame: Any) -> None:
    """The fixture must render through the generic adapter, unmodified."""
    row = frame.iloc[0]
    _require(
        row["source_url"] == EXPECTED_SOURCE_URL,
        f"canonical identity changed in the view model: {row['source_url']!r}",
    )
    _require(
        row["source_native_ids"]["legacy_document_id"] == EXPECTED_LEGACY_ID,
        "legacy source identifier was dropped by the view model",
    )
    _require(
        row["raw_metadata"]["legacy_optional_field"] == EXPECTED_LEGACY_FIELD,
        "legacy optional source metadata was dropped by the view model",
    )


def check_multimodal_shaped_fields(frame: Any) -> None:
    """Optional multimodal-shaped content must survive into the view model."""
    row = frame.iloc[0]
    _require(row["transcript"] == "A synthetic transcript segment.", "transcript was dropped")
    _require(row["ocr"] == ["SYNTHETIC ONLY"], "ocr observations were dropped")
    _require(
        row["frames"][0]["media_ref"].startswith("fixture://"),
        "frame references were dropped or rewritten",
    )
    _require(
        row["media_references"][0]["ref"].startswith("fixture://"),
        "media references were dropped or rewritten",
    )


def check_analysis_metadata_preserved(frame: Any) -> None:
    """Provenance, uncertainty, codebook and model metadata must be preserved."""
    row = frame.iloc[0]
    _require(row["uncertainties"][0]["value"] == 0.64, "uncertainty was dropped")
    _require(
        row["codebook_refs"][0]["id"] == "synthetic-codebook",
        "codebook references were dropped",
    )
    _require(row["model_runs"][0]["model"] == "fixture-model", "model provenance was dropped")
    _require(
        row["provenance"][-1]["provenance_id"] == "prov_analysis_001",
        "analysis provenance was dropped",
    )


def check_review_state_is_human_controlled(frame: Any) -> None:
    """Render must not promote provisional interpretation."""
    row = frame.iloc[0]
    _require(
        row["review_status"] == "PROVISIONAL",
        "document review state was promoted during rendering",
    )
    _require(
        row["analysis_objects"][0]["review_status"] == "PROVISIONAL",
        "candidate interpretation review state was promoted during rendering",
    )
    _require(
        row["analysis_objects"][0]["epistemic_type"] == "CANDIDATE_INTERPRETATION",
        "epistemic type was dropped or rewritten during rendering",
    )
    _require(
        row["evidence"][0]["provenance_id"] == "prov_analysis_001",
        "evidence provenance was dropped",
    )


def check_view_models_build(frame: Any) -> None:
    """Monitor and Explore view models must build from the fixture unmodified."""
    from laclaugpt_visualization.transforms import explore, monitor

    metrics = monitor(frame)
    _require(metrics["documents"] == 1, f"monitor document count wrong: {metrics}")
    _require(metrics["analyzed"] == 1, f"monitor analyzed count wrong: {metrics}")
    _require(
        metrics["awaiting_review"] == 1,
        "monitor must count provisional records as awaiting review",
    )

    views = explore(frame)
    _require(
        views["formations"].iloc[0]["formations"] == "synthetic formation",
        "explore formation view lost the fixture value",
    )
    _require(
        views["topics"].iloc[0]["topics"] == "synthetic governance",
        "explore topic view lost the fixture value",
    )


def check_sqlite_path(tmp_path: Path, payload: dict[str, Any]) -> None:
    """The generic adapter must also read a local SQLite canonical store."""
    import sqlite3

    from laclaugpt_visualization.data import load_sqlite

    path = tmp_path / "records.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE annotations (source_url TEXT PRIMARY KEY, record_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO annotations (source_url, record_json) VALUES (?, ?)",
            (payload["source_url"], json.dumps(payload)),
        )
    frame = load_sqlite(path)
    _require(len(frame) == 1, "sqlite path must reconstruct the single fixture record")
    _require(
        frame.iloc[0]["source_url"] == EXPECTED_SOURCE_URL,
        "sqlite path lost the canonical identity",
    )


def check_public_tree_policy() -> None:
    """The repository's own public-tree hygiene gate must pass."""
    import subprocess

    script = REPOSITORY_ROOT / "scripts" / "check_public_tree.py"
    _require(script.is_file(), f"public-tree policy script missing: {script}")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    _require(
        result.returncode == 0,
        f"public-tree policy check failed: {result.stdout.strip() or result.stderr.strip()}",
    )


def main(argv: list[str] | None = None) -> int:
    import tempfile

    parser = argparse.ArgumentParser(
        description="Offline Visualization contract-conformance check."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="path to the shared canonical parity fixture",
    )
    args = parser.parse_args(argv)

    payload = _load_fixture(args.fixture)
    frame = _load_frame(args.fixture)

    checks: list[tuple[str, Any]] = [
        ("generic render without a project adapter", lambda: check_generic_render(frame)),
        ("multimodal-shaped fields", lambda: check_multimodal_shaped_fields(frame)),
        ("analysis metadata preserved", lambda: check_analysis_metadata_preserved(frame)),
        (
            "review state is human-controlled",
            lambda: check_review_state_is_human_controlled(frame),
        ),
        ("monitor/explore view models", lambda: check_view_models_build(frame)),
        ("public-tree policy", check_public_tree_policy),
    ]

    failures: list[str] = []
    for name, check in checks:
        try:
            check()
        except CheckFailure as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - report any defect, never crash
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            check_sqlite_path(Path(tmp), payload)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"sqlite adapter path: {type(exc).__name__}: {exc}")
        print(f"ERROR sqlite adapter path: {type(exc).__name__}: {exc}")
    else:
        print("ok    sqlite adapter path")

    if failures:
        print(f"\n{len(failures)} contract check(s) failed")
        return 1
    print("\nall Visualization contract checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
