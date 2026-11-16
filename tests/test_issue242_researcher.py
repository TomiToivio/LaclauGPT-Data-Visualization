"""Issue #242 researcher output never exposes internal dataframe fields."""
import pandas as pd

from laclaugpt_visualization.ep24_researcher import (
    DNA_FIELDS,
    coverage,
    friendly,
    processed_export_warnings,
    research_children,
    view,
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

def test_processed_500_video_export_requires_actual_counts_and_unique_ids():
    frame = pd.DataFrame([
        {"country": country, "video_id": f"{i}"}
        for country in ("FI", "PL", "PT")
        for i in range(500)
    ])
    assert processed_export_warnings(frame, {}) == []
    assert processed_export_warnings(frame, {"dataset": "ep2024_reprocess"}) == []


def test_processed_export_rejects_wrong_counts_and_duplicates():
    frame = pd.DataFrame([{"country": "FI", "video_id": "same"}] * 500)
    warnings = processed_export_warnings(frame, {})
    assert any("Poland" in item for item in warnings)
    assert any("Portugal" in item for item in warnings)
    assert any("duplicate" in item.lower() for item in warnings)


def test_processed_export_checks_manifest_counts_but_never_requires_roster():
    frame = pd.DataFrame([
        {"country": country, "_storage_id": f"{country}:{i}"}
        for country in ("finland", "poland", "portugal") for i in range(500)
    ])
    assert not processed_export_warnings(frame, {"countries": {
        c: {"exported_videos": 500} for c in ("finland", "poland", "portugal")
    }})
    assert any("Manifest" in issue for issue in processed_export_warnings(
        frame, {"countries": {"poland": {"exported_videos": 499}}}))


def test_a_country_short_of_500_is_named_as_measured():
    """#252's intent, on the surviving function: a short country is reported, not policed."""
    frame = pd.DataFrame([{"country": "FI", "video_id": f"{i}"} for i in range(498)]
                         + [{"country": "PL", "video_id": f"{i}"} for i in range(500)]
                         + [{"country": "PT", "video_id": f"{i}"} for i in range(500)])
    warnings = processed_export_warnings(frame, {})
    assert any("Finland" in item and "498" in item for item in warnings)


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
