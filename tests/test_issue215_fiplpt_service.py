"""Issue #215: the deployed FI/PL/PT service must read the export's real manifest shape.

The authorized export writes ``record_counts`` keyed by full country name
(``finland``/``poland``/``portugal``) while the dashboard named countries by ISO code
(``fi``/``pl``/``pt``). The lookup therefore never matched, and the live service warned
"Countries not represented by this export: fi, pl, pt" on a corpus that contains all three.

A warning that fires on complete data is the same defect class as a chart that renders an
absent stage as a result: it teaches the reader to ignore the indicator. These tests pin the
manifest shape tolerance and the service template's safe defaults.

Fixtures are synthetic: real research data never enters this repository.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_visualization.ep24_reprocessed import (
    exported_counts,
    missing_countries,
)

# The shape the exporter actually emits (verified against the deployed export's MANIFEST.json).
NAMESPACED = {
    "generated_at": "2026-10-27T10:39:35+00:00",
    "exporter_version": "ep24-export-streaming/0.2",
    "record_unit": "video",
    "record_counts": {
        "exported_total": 4866,
        "finland": {"read": 3700, "exported": 2125, "duplicates": 1575, "invalid_ids": 0},
        "poland": {"read": 3643, "exported": 1781, "duplicates": 1862, "invalid_ids": 0},
        "portugal": {"read": 1946, "exported": 960, "duplicates": 986, "invalid_ids": 0},
    },
}


class ExportedCountTests(unittest.TestCase):
    def test_full_country_names_resolve_from_iso_codes(self) -> None:
        self.assertEqual(exported_counts(NAMESPACED), {"fi": 2125, "pl": 1781, "pt": 960})

    def test_iso_keyed_and_flat_counts_are_accepted(self) -> None:
        manifest = {"record_counts": {"fi": 10, "pl": 5, "pt": 0}}
        self.assertEqual(exported_counts(manifest), {"fi": 10, "pl": 5, "pt": 0})

    def test_absent_counts_are_not_zero_counts(self) -> None:
        self.assertEqual(exported_counts({}), {})


class MissingCountryTests(unittest.TestCase):
    def test_a_complete_export_does_not_warn(self) -> None:
        # Regression: the deployed app reported fi, pl and pt as absent on 4,866 exported records.
        self.assertEqual(missing_countries(NAMESPACED), [])

    def test_a_country_with_no_exported_records_is_reported(self) -> None:
        manifest = {"record_counts": {"finland": {"exported": 2125},
                                      "poland": {"exported": 0},
                                      "portugal": {"exported": 960}}}
        self.assertEqual(missing_countries(manifest), ["pl"])

    def test_a_manifest_without_counts_asserts_nothing(self) -> None:
        self.assertEqual(missing_countries({"generated_at": "unknown"}), [])


class DeployedAppContractTests(unittest.TestCase):
    def test_app_uses_the_shape_tolerant_helper(self) -> None:
        source = (ROOT / "src" / "laclaugpt_visualization"
                  / "ep24_reprocessed_app.py").read_text(encoding="utf-8")
        self.assertIn("missing_countries(manifest)", source)
        # The ISO-only inline comprehension is what produced the false warning.
        self.assertNotIn('for country in ("fi", "pl", "pt")', source)

    def test_service_template_never_binds_every_interface(self) -> None:
        template = (ROOT / "deploy" / "ep24-fiplpt.service.example").read_text(encoding="utf-8")
        directives = [line for line in template.splitlines() if not line.lstrip().startswith("#")]
        self.assertFalse(any("0.0.0.0" in line for line in directives))
        self.assertIn("--server.address ${BIND_ADDR}", template)
        self.assertIn("Restart=on-failure", template)
        self.assertIn("WantedBy=default.target", template)


if __name__ == "__main__":
    unittest.main()
