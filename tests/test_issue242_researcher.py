"""Issue #242 researcher output never exposes internal dataframe fields."""
import pandas as pd
from laclaugpt_visualization.ep24_researcher import (
    view, friendly, cohort_warnings, coverage, research_children, DNA_FIELDS,
    EXPECTED_DATASET,
)

def test_allowlist_excludes_processing_and_download_secrets():
    frame = pd.DataFrame([{
        "country": "Finland", "video_id": "abc", "summary_analysis": "Research finding",
        "_storage_id": "private-row-id", "worker_token": "secret",
        "checkpoint_path": "/secret/path", "raw_prompt": "not-for-researcher",
    }])
    for full in (False, True):
        displayed = view(frame, full=full)
        csv = displayed.to_csv(index=False)
        assert "Finland" in csv
        assert "private-row-id" not in csv
        assert "secret" not in csv
        assert "checkpoint" not in csv.lower()
        assert "raw_prompt" not in csv
        assert "_storage_id" not in csv

def test_structured_evidence_is_readable():
    result = friendly('[{"actor":"Party","stance":"support"}]')
    assert "Actor: Party" in result
    assert "Stance: support" in result
    assert not result.startswith("[")

def test_monday500_verified_only_with_manifest_and_counts():
    frame = pd.DataFrame([{"country": "FI", "dataset": EXPECTED_DATASET}])
    warnings = cohort_warnings(frame, {"dataset": EXPECTED_DATASET})
    assert any("Finland: 1" in item for item in warnings)
    assert any("Poland: 0" in item for item in warnings)
    assert any("Portugal: 0" in item for item in warnings)
    assert any("manifest" in item.lower() for item in cohort_warnings(frame, {}))

def test_unknown_dataset_rejected_even_if_row_count_matches():
    frame = pd.DataFrame([{"country": country, "dataset": "other"}
                          for country in ("FI", "PL", "PT") for _ in range(500)])
    assert any("another dataset" in item for item in
               cohort_warnings(frame, {"dataset": EXPECTED_DATASET}))

def test_stage_coverage_denominators_and_no_fabricated_success():
    results = coverage(pd.DataFrame([{"video_id": "x"}, {"video_id": "y"}]))
    assert not results.empty
    assert set(results["Denominator"]) == {2}
    assert results[results["Step"] == 7]["Videos"].sum() == 2

def test_child_table_allowlist():
    output = research_children([{"actor": "A", "concept": "C",
                                 "worker_token": "not-visible"}], DNA_FIELDS)
    assert "Actor" in output.columns
    assert "not-visible" not in output.to_csv(index=False)
