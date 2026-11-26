"""Synthetic tests for AI26 researcher display, independent of MongoDB and Laskin."""
import pandas as pd

from laclaugpt_visualization.ai26_research_ux import (
    MISSING,
    category_counts,
    overlap_matrix,
    publication_activity,
    readable,
    researcher_table,
    source_link,
    utc_dates,
    valid_revision,
)


def test_researcher_allowlist_hides_machine_fields_and_reports_actual_time():
    frame = pd.DataFrame([
        {
            "content_title": "Synthetic record",
            "source_timestamp": "2026-01-02T01:30:00+02:00",
            "document_id": "internal",
            "raw_payload": {"secret": "private"},
        },
        {"content_title": None, "source_timestamp": "invalid"},
    ])
    table = researcher_table(frame)
    assert list(table) == ["Title", "Published (UTC)"]
    assert table.iloc[0].tolist() == ["Synthetic record", "2026-01-01 23:30"]
    assert table.iloc[1].tolist() == ["", ""]
    assert utc_dates(frame).isna().sum() == 1
    assert not len(researcher_table(pd.DataFrame({"internal": [1]})).columns)


def test_missing_categories_remain_visible():
    frame = pd.DataFrame({"status": ["complete", "", None, "complete"]})
    counts = category_counts(frame, "status").set_index("Label")["Records"]
    assert counts.to_dict() == {"complete": 2, MISSING: 2}
    assert category_counts(frame, "other").iloc[0].tolist() == [MISSING, 4]
    assert category_counts(pd.DataFrame(), "other").empty


def test_publication_activity_keeps_unknown_source_but_excludes_unknown_date():
    frame = pd.DataFrame({
        "source_timestamp": [
            "2026-01-01T01:00:00Z", "2026-01-01T15:00:00Z",
            "2026-01-03T00:00:00Z", "unknown",
        ],
        "source_platform": ["Synthetic A", "Synthetic A", None, "Synthetic B"],
    })
    counts = publication_activity(frame)
    assert counts["Records"].sum() == 3
    assert len(counts) == 2
    assert set(counts["Source"]) == {"Synthetic A", MISSING}
    assert counts["Day"].dt.day.tolist() == [1, 3]
    assert publication_activity(pd.DataFrame()).empty


def test_overlap_uses_only_observed_counts_and_handles_empty_input():
    cross = pd.DataFrame({
        "formation": ["F1", "F1", "F2"],
        "signifier": ["S1", "S2", "S1"],
        "count": [4, 1, 2],
    })
    matrix = overlap_matrix(cross)
    assert matrix.loc["F1", "S1"] == 4
    assert matrix.loc["F2", "S2"] == 0
    assert matrix.to_numpy().sum() == 7
    assert overlap_matrix(cross, limit=1).shape == (1, 1)
    assert overlap_matrix(pd.DataFrame()).empty


def test_nested_evidence_is_readable_without_exposing_machine_fields():
    text = readable([{"quote": "<script>literal source text</script>", "hash": "internal"}])
    assert "<script>literal source text</script>" in text
    assert "internal" not in text
    assert readable(pd.NA) == ""
    assert readable(float("nan")) == ""


def test_safe_links_and_revision_labels():
    assert source_link("https://example.invalid/a(b)") == "https://example.invalid/a%28b%29"
    assert source_link("javascript:alert(1)") is None
    assert source_link("urn:record:synthetic") is None
    assert valid_revision("12abCDE") == "12abcde"
    assert valid_revision("/tmp/private") is None
    assert valid_revision("bad") is None
