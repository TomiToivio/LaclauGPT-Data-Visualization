"""Issue #205: the two EP24 exporters must agree on the unit of analysis.

`export_visualization_data.py` and `export_streaming.py` produced two different record universes
(6,825 vs 5,306) because each had its own definition of "one record". The contract is now explicit:

* ``video``  -- one record per media file; repeated ingest runs collapse to one.
* ``ingest`` -- one record per pipeline run (``_storage_id``).

Both exporters must group **identically** for the same unit. These tests pin that, using the real
exporters loaded from their script paths rather than a reimplementation of them.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "scripts" / "ep24" / "export_visualization_data.py"
STREAMING = ROOT / "scripts" / "ep24" / "export_streaming.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve annotations through sys.modules[cls.__module__]; register before exec
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


canonical = _load(CANONICAL, "ep24_canonical_exporter")
streaming = _load(STREAMING, "ep24_streaming_exporter")


#: Two media files, with one video re-ingested three times: 4 ingest rows, 2 distinct videos.
ROWS = [
    {"_storage_id": "s1", "allas_filename": "a.mp4", "video_id": "v1", "country": "finland"},
    {"_storage_id": "s2", "allas_filename": "a.mp4", "video_id": "v1", "country": "finland"},
    {"_storage_id": "s3", "allas_filename": "a.mp4", "video_id": "v1", "country": "finland"},
    {"_storage_id": "s4", "allas_filename": "b.mp4", "video_id": "v2", "country": "finland"},
]


def _canonical_groups(unit: str) -> int:
    keys = {canonical.row_identity(row, unit) for row in ROWS}
    keys.discard("")
    return len(keys)


def _streaming_groups(unit: str) -> int:
    keys = {streaming.identity_key("finland", row, unit=unit) for row in ROWS}
    keys.discard("")
    return len(keys)


@pytest.mark.parametrize("unit,expected", [("video", 2), ("ingest", 4)])
def test_both_exporters_agree_on_the_group_count(unit: str, expected: int) -> None:
    assert _canonical_groups(unit) == expected
    assert _streaming_groups(unit) == expected


def test_the_two_units_really_differ_on_this_corpus() -> None:
    # If these ever coincide, the fixture stopped testing anything.
    assert _canonical_groups("video") != _canonical_groups("ingest")


def test_unknown_unit_is_rejected_by_both() -> None:
    with pytest.raises(ValueError):
        canonical.row_identity(ROWS[0], "episode")
    with pytest.raises(ValueError):
        streaming.identity_key("finland", ROWS[0], unit="episode")


def test_a_row_with_no_identity_at_all_is_unusable_in_both_units() -> None:
    # The two exporters must agree on which rows are dropped, or their counts drift for that reason
    # instead of for the reason the issue is about.
    empty = {"_storage_id": "", "allas_filename": "", "video_id": "", "country": "finland"}
    assert canonical.row_identity(empty, "video") == ""
    assert canonical.row_identity(empty, "ingest") == ""
    assert streaming.identity_key("finland", empty, unit="video") == ""
    assert streaming.identity_key("finland", empty, unit="ingest") == ""


def test_ingest_falls_back_to_video_id_in_both_exporters() -> None:
    no_storage = {"_storage_id": "", "allas_filename": "c.mp4", "video_id": "v3"}
    assert canonical.row_identity(no_storage, "ingest")
    assert streaming.identity_key("finland", no_storage, unit="ingest")


def test_streaming_manifest_records_the_unit_and_distinct_media(tmp_path: Path) -> None:
    source = tmp_path / "fi.csv"
    columns = ["_storage_id", "allas_filename", "video_id", "country"]
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(ROWS)

    output = tmp_path / "out"
    rc = streaming.main([
        "--source", f"finland={source}", "--output", str(output),
        "--record-unit", "ingest", "--allow-unaccounted",
    ])
    assert rc == 0

    manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["record_unit"] == "ingest"
    assert manifest["distinct_media"] == 2, "two media files, despite four ingest runs"
    assert manifest["record_counts"]["finland"]["exported"] == 4


def test_streaming_video_unit_collapses_the_reingests(tmp_path: Path) -> None:
    source = tmp_path / "fi.csv"
    columns = ["_storage_id", "allas_filename", "video_id", "country"]
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(ROWS)

    output = tmp_path / "out"
    rc = streaming.main([
        "--source", f"finland={source}", "--output", str(output),
        "--record-unit", "video", "--allow-unaccounted",
    ])
    assert rc == 0

    manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["record_unit"] == "video"
    assert manifest["record_counts"]["finland"]["exported"] == 2
    assert manifest["distinct_media"] == 2
