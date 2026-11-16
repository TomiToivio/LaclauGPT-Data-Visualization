"""The EP24 dashboard must read the bundle the checkpoint exporter actually writes (#242).

#242 requires the researcher dashboard to serve the real FI/PL/PT 500-video cohort and to
*differentiate* not-run, successful and errored stages instead of flattening them into one number.
The export that the producer's checkpoints produce (`ep24_export.py`) writes its manifest as
`manifest.json` with `countries[<country>].stages` outcome counts, while the older #210 Mongo refresh
wrote `MANIFEST.json` with `record_counts`/`stage_coverage`. Before this, the dashboard read only the
second shape, so a real 1,500-record bundle reported "no MANIFEST.json" and no coverage at all.

These tests pin both shapes against synthetic manifests — no private data.
"""
from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_visualization.ep24_reprocessed import (
    coverage_rows,
    exported_counts,
    read_manifest,
    stage_outcomes,
)

CHECKPOINT_MANIFEST = {
    "version": "ep24-export/2",
    "exported_at": "2026-11-15T19:00:00+00:00",
    "all_requested_countries_present": True,
    "countries": {
        "finland": {
            "exported_videos": 500, "input_rows": 500,
            "collection": "monday500_20261031_finland",
            "stages": {
                "0": {"output_present": 500},
                "1": {"cached": 16, "ok": 484},
                "4": {"OK": 500},
                "7": {"ok": 500},
                "8": {"ok": 472, "error": 1, "not_exported": 27},
                "9": {"not_exported": 500},
            },
        },
        "poland": {
            "exported_videos": 500, "input_rows": 500,
            "stages": {"7": {"ok": 6, "error": 4, "not_exported": 490}},
        },
    },
}

MONGO_MANIFEST = {
    "record_counts": {"finland": {"exported": 500}, "poland": {"exported": 500}},
    "stage_coverage": {"finland": {"7": {"records": 400}}, "poland": {"7": {"records": 0}}},
    "inputs": {"finland": {"profile": "reprocessed"},
               "poland": {"profile": "reprocessed", "stage_unavailable": ["7"]}},
    "builder_version": "ep24-bundle/1",
}


# ---------------------------------------------------------------- manifest discovery


def test_both_manifest_spellings_are_read(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(json.dumps(CHECKPOINT_MANIFEST), encoding="utf-8")
    assert read_manifest(tmp_path)["version"] == "ep24-export/2"

    other = tmp_path / "mongo"
    other.mkdir()
    (other / "MANIFEST.json").write_text(json.dumps(MONGO_MANIFEST), encoding="utf-8")
    assert read_manifest(other)["builder_version"] == "ep24-bundle/1"


def test_a_manifest_in_data_subfolder_is_found(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text(json.dumps(CHECKPOINT_MANIFEST))
    assert read_manifest(tmp_path)["version"] == "ep24-export/2"


def test_no_manifest_stays_empty(tmp_path: Path):
    assert read_manifest(tmp_path) == {}


# ---------------------------------------------------------------- exported counts


def test_counts_come_from_the_checkpoint_shape():
    assert exported_counts(CHECKPOINT_MANIFEST) == {"fi": 500, "pl": 500, "pt": 0}


def test_counts_still_come_from_the_mongo_shape():
    assert exported_counts(MONGO_MANIFEST) == {"fi": 500, "pl": 500, "pt": 0}


def test_absent_counts_are_empty_not_zero(tmp_path: Path):
    assert exported_counts({"version": "x"}) == {}


# ---------------------------------------------------------------- stage outcomes


def test_outcome_keys_are_classified_case_insensitively():
    assert stage_outcomes({"OK": 500})["present"] == 500
    assert stage_outcomes({"cached": 16, "ok": 484})["present"] == 500
    assert stage_outcomes({"output_present": 500})["present"] == 500


def test_errors_and_never_produced_are_kept_apart():
    totals = stage_outcomes({"ok": 472, "error": 1, "not_exported": 27})
    assert totals == {"present": 472, "error": 1, "skipped": 0, "not_exported": 27, "other": 0}


def test_a_mongo_shaped_stage_is_a_single_present_count():
    assert stage_outcomes({"records": 400})["present"] == 400


# ---------------------------------------------------------------- coverage rows


def rows_by(country: str, stage: str, rows: list[dict]) -> dict:
    return next(row for row in rows if row["country"] == country and row["stage"] == stage)


def test_checkpoint_coverage_reports_partial_and_unavailable_stages():
    rows = coverage_rows(CHECKPOINT_MANIFEST)

    fi8 = rows_by("finland", "8", rows)
    assert fi8["records"] == 472 and fi8["denominator"] == 500
    assert fi8["coverage_pct"] == 94.4
    assert fi8["availability"] == "partial"
    assert fi8["errored"] == 1 and fi8["not_exported"] == 27

    fi9 = rows_by("finland", "9", rows)
    assert fi9["records"] == 0
    assert fi9["coverage_pct"] is None
    assert fi9["availability"] == "unavailable in this source"

    pl7 = rows_by("poland", "7", rows)
    assert (pl7["records"], pl7["errored"], pl7["not_exported"]) == (6, 4, 490)
    assert pl7["availability"] == "partial"


def test_a_fully_present_stage_reads_present():
    rows = coverage_rows(CHECKPOINT_MANIFEST)
    assert rows_by("finland", "7", rows)["availability"] == "present"


def test_the_mongo_shape_still_renders_its_unavailable_marker():
    rows = coverage_rows(MONGO_MANIFEST)
    assert rows_by("finland", "7", rows)["coverage_pct"] == 80.0
    unavailable = rows_by("poland", "7", rows)
    assert unavailable["availability"] == "unavailable in this source"
    assert unavailable["coverage_pct"] is None


def test_coverage_of_an_empty_manifest_is_empty():
    assert coverage_rows({}) == []
