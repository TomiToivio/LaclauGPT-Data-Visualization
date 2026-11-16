"""Synthetic contract tests for #263; no restricted EP24 rows."""
import pandas as pd

from laclaugpt_visualization.ep24_legacy_workbench import (
    AGGREGATE_TABS,
    NO_SOURCE,
    RECORD_FIELDS,
    RECORD_TABS,
    available_aggregates,
    child_labels,
)


def test_every_legacy_record_tab_has_display_fields():
    assert len(RECORD_TABS) == 9
    assert set(RECORD_TABS) == set(RECORD_FIELDS)
    assert all(RECORD_FIELDS[name] for name in RECORD_TABS)


def test_every_legacy_aggregate_is_mapped_or_explicitly_unavailable():
    frame = pd.DataFrame([{
        "country": "Finland", "political_preference": "unknown",
        "postprocess_themes": "[]", "postprocess_entities": "[]",
        "source_language": "fi", "positive": 0.2,
    }])
    exposed = set(available_aggregates(frame))
    assert len(AGGREGATE_TABS) == 9
    assert exposed | set(NO_SOURCE) == set(AGGREGATE_TABS)
    assert not exposed & set(NO_SOURCE)


def test_no_manifestoberta_or_lda_tab_without_source():
    frame = pd.DataFrame({"country": ["Finland"]})
    assert "Topics" not in available_aggregates(frame)
    assert "ManifestoBERTa" not in available_aggregates(frame)
    assert "Sentiments" not in available_aggregates(frame)
    assert "Languages" not in available_aggregates(frame)


def test_child_joins_are_country_scoped(tmp_path):
    target = tmp_path / "finland" / "children"
    target.mkdir(parents=True)
    (target / "themes.csv").write_text(
        "source_record_id,name\\nID-1,justice\\nID-2,other\\n", encoding="utf-8"
    )
    source = {"country": "finland", "_storage_id": "ID-1"}
    assert child_labels(tmp_path, source, "themes") == ["justice"]
    assert child_labels(tmp_path, {"country": "poland", "_storage_id": "ID-1"}, "themes") == []
    assert child_labels(tmp_path, {"country": "finland"}, "themes") == []
