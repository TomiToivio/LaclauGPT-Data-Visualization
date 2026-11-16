"""The cohort guard against the export that actually exists (#242).

The #243/#245 guard required every row's ``dataset`` column to equal the cohort name. On the real
checkpoint export that column holds the *pipeline* label (``ep2024_reprocess``) while the cohort is
named by ``_storage_id`` (``monday500:<country>:<id>``) and by the manifest's ``producer_revision``
(``monday500_20261031``). The guard therefore rejected all 1 500 delivered videos: an app that
fails closed on correct data is an outage with good intentions.

These tests pin the corrected reading, using rows shaped exactly like the delivered export.
"""
from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.ep24_cohort import is_member
from laclaugpt_visualization.ep24_researcher import (
    EXPECTED_DATASET,
    cohort_notes,
    cohort_warnings,
    declared_run,
)

MANIFEST = {
    "version": "ep24-final-export-v1",
    "producer_revision": "monday500_20261031",
    "exported_at": "2026-11-15T19:00:00+00:00",
    "countries": {
        "finland": {"input_rows": 500, "exported_videos": 500},
        "poland": {"input_rows": 500, "exported_videos": 500},
        "portugal": {"input_rows": 500, "exported_videos": 500},
    },
    "approved_cohort": {
        "schema": "ep24-approved-cohort/1",
        "dataset": EXPECTED_DATASET,
        "sha256": "88f39120829d523d" * 4,
        "approved_counts": {"finland": 500, "poland": 500, "portugal": 500},
    },
}


def rows(count: int = 500) -> pd.DataFrame:
    records = []
    for country in ("finland", "poland", "portugal"):
        for index in range(count):
            records.append(
                {
                    "_storage_id": f"monday500:{country}:{index:024x}",
                    "country": country,
                    "dataset": "ep2024_reprocess",
                    "video_id": f"HEPP24-{country}-{index}",
                }
            )
    return pd.DataFrame(records)


def test_the_manifest_names_the_cohort_by_producer_revision():
    """The checkpoint exporter writes producer_revision, not dataset: both must resolve."""
    assert declared_run(MANIFEST) == EXPECTED_DATASET
    assert declared_run({"dataset": EXPECTED_DATASET}) == EXPECTED_DATASET
    assert declared_run({"approved_cohort": {"dataset": EXPECTED_DATASET}}) == EXPECTED_DATASET
    assert declared_run({}) == ""


def test_a_correct_export_passes_the_cohort_gate():
    warnings = cohort_warnings(rows(), MANIFEST)
    assert warnings == [], warnings


def test_the_pipeline_label_is_reported_as_provenance_not_as_a_blocker():
    notes = cohort_notes(rows(), MANIFEST)
    assert any("ep2024_reprocess" in note for note in notes)
    assert any("ep24_monday500_20261031" in note for note in notes)
    assert any("sha256" in note for note in notes)


def test_membership_is_decided_by_the_roster_and_the_storage_key():
    approved = {f"monday500:finland:{index:024x}" for index in range(500)}
    assert is_member({"_storage_id": "monday500:finland:" + f"{0:024x}", "country": "finland",
                      "dataset": "ep2024_reprocess"}, "finland", approved)
    assert not is_member({"_storage_id": "monday500:finland:deadbeef", "country": "finland"},
                         "finland", approved)
    assert not is_member({"_storage_id": "monday500:poland:" + f"{0:024x}", "country": "finland"},
                         "finland", approved)


def test_a_missing_country_is_still_a_blocking_warning():
    frame = rows().iloc[:1000]
    warnings = cohort_warnings(frame, MANIFEST)
    assert any("Portugal" in warning for warning in warnings)


def test_a_manifest_without_any_identifier_still_warns():
    warnings = cohort_warnings(rows(), {})
    assert any("No export manifest" in warning for warning in warnings)
    assert any("no verifiable dataset identifier" in warning for warning in warnings)
