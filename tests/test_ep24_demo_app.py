"""Issue #195 Part 2: the dashboard's manifest/coverage contract.

The app must never assert coverage it cannot prove: an absent manifest is reported, an unavailable
stage is not rendered as 0 %, and a denominator of zero is not a completion rate.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_visualization.ep24_reprocessed import (  # noqa: E402
    coverage_rows, read_manifest, status,
)

MANIFEST = {
    "builder_version": "ep24-export-1",
    "generated_at": "2026-10-26T12:00:00+00:00",
    "record_counts": {
        "finland": {"read": 3700, "exported": 2125, "duplicates": 1575, "invalid_ids": 0},
        "poland": {"read": 2214, "exported": 2112, "duplicates": 102, "invalid_ids": 0},
    },
    "stage_coverage": {
        "finland": {"1_preprocess": {"records": 2658, "pct_of_exported": 100.0},
                    "6_discourse": {"records": 724, "pct_of_exported": 34.1},
                    "9_rdf": {"records": 0, "pct_of_exported": 0.0}},
        "poland": {"1_preprocess": {"records": 0, "pct_of_exported": 0.0}},
    },
    "inputs": {
        "finland": {"profile": "reprocessed", "stage_unavailable": ["9_rdf"]},
        "poland": {"profile": "legacy",
                   "stage_unavailable": ["0_ingest", "1_preprocess", "2_frame", "3_video",
                                         "4_summary", "5_postprocess", "6_discourse", "7_dna",
                                         "8_sna", "9_rdf"]},
    },
}


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_missing_manifest_is_empty_not_invented(self) -> None:
        self.assertEqual(read_manifest(self.root), {})

    def test_manifest_is_found_in_root_and_data_subdirectory(self) -> None:
        (self.root / "MANIFEST.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        self.assertEqual(read_manifest(self.root)["builder_version"], "ep24-export-1")
        nested = self.root / "data"
        nested.mkdir()
        (self.root / "MANIFEST.json").unlink()
        (nested / "MANIFEST.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        self.assertEqual(read_manifest(self.root)["builder_version"], "ep24-export-1")

    def test_unavailable_stage_has_no_percentage(self) -> None:
        rows = coverage_rows(MANIFEST)
        rdf = next(r for r in rows if r["country"] == "finland" and r["stage"] == "9_rdf")
        self.assertIsNone(rdf["coverage_pct"])
        self.assertEqual(rdf["availability"], "unavailable in this source")

    def test_legacy_country_reports_every_reprocessed_stage_as_unavailable(self) -> None:
        rows = coverage_rows(MANIFEST)
        poland = [r for r in rows if r["country"] == "poland"]
        self.assertEqual({r["profile"] for r in poland}, {"legacy"})
        self.assertTrue(all(r["availability"] == "unavailable in this source" for r in poland))

    def test_denominator_is_the_countrys_exported_records(self) -> None:
        rows = coverage_rows(MANIFEST)
        discourse = next(r for r in rows if r["country"] == "finland" and r["stage"] == "6_discourse")
        self.assertEqual(discourse["denominator"], 2125)
        self.assertEqual(discourse["coverage_pct"], 34.1)


class StatusTests(unittest.TestCase):
    def test_missing_stage_is_unavailable_and_never_guessed(self) -> None:
        self.assertEqual(status({}, 6), "unavailable")

    def test_status_strings_are_mapped_but_not_interpreted(self) -> None:
        self.assertEqual(status({"laclau_status": "ok"}, 6), "complete")
        self.assertEqual(status({"laclau_status": "error: timeout"}, 6), "error")
        self.assertEqual(status({"laclau_status": "skipped"}, 6), "skipped")

    def test_step_nine_depends_on_exported_rdf_files(self) -> None:
        self.assertEqual(status({}, 9, rdf_available=False), "unavailable")
        self.assertEqual(status({}, 9, rdf_available=True), "available")


if __name__ == "__main__":
    unittest.main()
