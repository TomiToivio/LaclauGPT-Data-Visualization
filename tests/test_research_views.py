import json

import pandas as pd

from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.research_views import (
    infer_dashboard_mode,
    load_reports,
    map_points,
    timeline_counts,
)


def test_infers_legacy_canonical_and_hybrid_modes() -> None:
    legacy = frame_from_records([
        {
            "new_id": "legacy-1",
            "whisper_transcript": "text",
            "summary_analysis": "summary",
        }
    ])
    assert infer_dashboard_mode(legacy) == "legacy_ep24"

    canonical = frame_from_records([
        {
            "schema_version": "1.0.0",
            "source_url": "https://example.invalid/1",
            "source": {"platform": "rss"},
            "content": {"text": "text"},
            "analysis": {"formations": [{"label": "critical-ai"}]},
            "provenance": [{"method": "synthetic"}],
        }
    ])
    assert infer_dashboard_mode(canonical) == "canonical_live"

    hybrid = canonical.copy()
    hybrid["whisper_transcript"] = "legacy transcript"
    hybrid["summary_analysis"] = "legacy summary"
    assert infer_dashboard_mode(hybrid) == "hybrid_research"


def test_map_points_discards_missing_and_invalid_coordinates() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_url": "https://example.invalid/a",
                "event_name": "Valid event",
                "event_location": "Helsinki",
                "event_lat": 60.1699,
                "event_lng": 24.9384,
                "event_date": "2026-09-16",
                "provenance": [{"method": "synthetic-geocoder"}],
            },
            {
                "source_url": "https://example.invalid/b",
                "event_name": "Invalid event",
                "event_lat": 200,
                "event_lng": 400,
            },
            {"source_url": "https://example.invalid/c", "event_name": "No coordinates"},
        ]
    )
    points = map_points(frame)
    assert points["source_url"].tolist() == ["https://example.invalid/a"]
    assert points.iloc[0]["location"] == "Helsinki"
    assert points.iloc[0]["provenance"][0]["method"] == "synthetic-geocoder"


def test_timeline_keeps_different_clocks_separate() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_url": "https://example.invalid/a",
                "source_timestamp": "2026-09-14T10:00:00Z",
                "collection_timestamp": "2026-09-15T10:00:00Z",
                "analysis_timestamp": "2026-09-16T10:00:00Z",
                "event_date": "2026-09-13",
            }
        ]
    )
    counts = timeline_counts(frame)
    assert set(counts["time_kind"]) == {"source", "collection", "analysis", "event"}
    assert counts["documents"].tolist() == [1, 1, 1, 1]


def test_reports_load_markdown_and_json_and_ignore_bad_json(tmp_path) -> None:
    (tmp_path / "2026-09-16.md").write_text("# Daily research report\n\nText", encoding="utf-8")
    (tmp_path / "2026-09-15.json").write_text(
        json.dumps(
            {
                "title": "Structured report",
                "date": "2026-09-15",
                "summary": "Summary",
                "source_urls": ["https://example.invalid/a"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    reports = load_reports(tmp_path)
    assert [report.title for report in reports] == ["Daily research report", "Structured report"]
    assert reports[1].source_urls == ("https://example.invalid/a",)
