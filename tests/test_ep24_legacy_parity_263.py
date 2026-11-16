"""Legacy parity is a claim, so it is tested (#263).

The claim in the issue is "the :8502 dashboard behaves like the legacy :8501 workbench". A claim like that
rots silently: a tab gets dropped, a column is renamed upstream, an unsupported tab starts rendering empty and
nobody notices. These tests pin the registry, the arithmetic, and the loader behaviour that makes the claim
meaningful.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from laclaugpt_visualization.ep24_legacy_parity import (
    AGGREGATE_SOURCES,
    AGGREGATE_TABS,
    FILTERS,
    NO_SOURCE_REASON,
    RECORD_SOURCES,
    RECORD_TABS,
    UNSUPPORTED_FILTERS,
    apply_filters,
    child_counts,
    duration_by,
    frequency_by,
    language_counts,
    load_children,
    parity_rows,
    record_tabs,
    scope_children,
    sentiment_counts,
    unsupported_tabs,
)


@pytest.fixture()
def parents() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_key": ["k1", "k2", "k3"],
            "country": ["finland", "finland", "poland"],
            "political_preference": ["right", "left", "right"],
            "source_type": ["tiktok", "instagram", "tiktok"],
            "asr_language": ["fi", "en", "pl"],
            "video_duration_seconds": [60, 120, 180],
            "timestamp": ["2024-05-01T10:00:00Z", "2024-05-02T10:00:00Z", "2024-06-01T10:00:00Z"],
            "positive": [1, 0, 3],
            "neutral": [0, 2, 0],
            "negative": [0, 1, 0],
            "researcher_note": ["", "checked", ""],
            "asr_transcript": ["a", "b", "c"],
        }
    )


@pytest.fixture()
def children() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_key": ["k1", "k1", "k2", "k3"],
            "field": ["postprocess_themes", "postprocess_entities", "postprocess_themes", "postprocess_entities"],
            "index": [0, 0, 0, 0],
            "item.label": ["elections", "Orpo", "elections", "Tusk"],
        }
    )


def test_every_legacy_record_tab_is_declared_with_a_source_or_a_reason():
    """A tab may be missing, but never undocumented: missing and unimplemented must look different."""
    assert set(RECORD_SOURCES) == set(RECORD_TABS)
    for tab, columns in RECORD_SOURCES.items():
        if columns is None:
            assert tab in NO_SOURCE_REASON, f"{tab} has no source and no reason"
        else:
            assert columns, f"{tab} declares an empty source list"


def test_every_legacy_aggregate_tab_is_declared_with_a_source_or_a_reason():
    assert set(AGGREGATE_SOURCES) == set(AGGREGATE_TABS)
    for tab, columns in AGGREGATE_SOURCES.items():
        if columns is None:
            assert tab in NO_SOURCE_REASON, f"{tab} has no source and no reason"


def test_the_two_tabs_with_no_reprocessed_source_are_named_explicitly():
    """ManifestoBERTa and LDA topics were legacy-only; silence about them is the defect."""
    assert set(unsupported_tabs()) == {"Topics", "ManifestoBERTa"}


def test_parity_rows_cover_both_views_in_legacy_order():
    rows = parity_rows()
    assert [row["tab"] for row in rows if row["view"] == "per-record"] == list(RECORD_TABS)
    assert [row["tab"] for row in rows if row["view"] == "aggregate"] == list(AGGREGATE_TABS)


def test_record_tabs_render_content_for_available_and_reason_for_unavailable(parents, children):
    tabs = record_tabs(parents.iloc[0].to_dict(), children)
    whisper = {block["label"]: block["value"] for block in tabs["Whisper"]["blocks"]}
    assert tabs["Whisper"]["available"] and whisper["Transcript (original)"] == "a"
    assert "elections" in tabs["Themes"]["blocks"][0]["value"]
    assert "Orpo" in tabs["Persons"]["blocks"][0]["value"]


def test_record_tabs_never_raise_on_a_record_missing_every_column(children):
    tabs = record_tabs({"source_key": "unknown"}, children)
    assert tabs["Metadata"]["available"]
    assert tabs["Themes"]["blocks"] == []
    assert tabs["Themes"]["empty"]  # the child table was read and had nothing for this record


def test_record_tab_content_names_only_columns_that_exist():
    """A renamed upstream column must show as absent, not as a KeyError or a silently empty tab."""
    tabs = record_tabs({"asr_transcript": "hello"})
    assert [block["label"] for block in tabs["Whisper"]["blocks"]] == ["Transcript (original)"]
    assert "Translation" in tabs["Whisper"]["absent"]


def test_absent_and_empty_are_reported_as_different_facts():
    """`asr_translation` present-but-blank is not the same as a column this export never carries."""
    tabs = record_tabs({"asr_transcript": "hello", "asr_translation": ""})
    whisper = tabs["Whisper"]
    assert [block["label"] for block in whisper["blocks"]] == ["Transcript (original)"]
    assert whisper["empty"] == ["Translation"]
    assert whisper["absent"] == []

    renamed = record_tabs({"speech_text": "hello"})
    assert renamed["Whisper"]["blocks"] == []
    assert renamed["Whisper"]["absent"] == ["Transcript (original)", "Translation"]


def test_platform_is_declared_as_a_derivation_unless_the_export_carries_it():
    derived = record_tabs({"country": "finland"})["Metadata"]
    labels = [block["label"] for block in derived["blocks"]]
    assert labels[:1] == ["Platform (derived)"]

    carried = record_tabs({"platform": "instagram", "country": "finland"})["Metadata"]
    assert "Platform (derived)" not in [block["label"] for block in carried["blocks"]]


def test_a_structured_cell_is_projected_through_the_display_allowlist():
    """A model cell must not be able to publish producer keys just because the tab renders it."""
    tabs = record_tabs(
        {"formula_of_populism_analysis": '{"interpretation": "people vs elite", "prompt": "SECRET"}'}
    )
    rendered = " ".join(block["value"] for block in tabs["Populism"]["blocks"])
    assert "people vs elite" in rendered
    assert "SECRET" not in rendered


def test_child_rows_are_matched_on_either_identifier_dialect():
    older = pd.DataFrame(
        {
            "parent_record_id": ["record-9"],
            "field": ["postprocess_themes"],
            "item.label": ["Matched by record id"],
        }
    )
    tabs = record_tabs({"record_id": "record-9"}, older)
    assert "Matched by record id" in tabs["Themes"]["blocks"][0]["value"]
    assert record_tabs({"record_id": "other"}, older)["Themes"]["blocks"] == []


def test_filters_are_conjunctive_and_empty_means_unrestricted(parents):
    assert len(apply_filters(parents)) == 3
    narrowed = apply_filters(parents, countries=["finland"], political_preferences=["left"])
    assert list(narrowed["source_key"]) == ["k2"]


def test_duration_and_date_filters_use_the_declared_columns(parents):
    by_duration = apply_filters(parents, duration=(100, 200))
    assert list(by_duration["source_key"]) == ["k2", "k3"]
    by_date = apply_filters(parents, dates=(pd.Timestamp("2024-05-02").date(), pd.Timestamp("2024-05-02").date()))
    # The end date is a whole day, not midnight — the legacy behaviour a naive filter gets wrong.
    assert list(by_date["source_key"]) == ["k2"]


def test_search_needs_a_named_column(parents):
    assert len(apply_filters(parents, search="checked")) == 3
    assert list(apply_filters(parents, search="checked", search_column="researcher_note")["source_key"]) == ["k2"]


def test_frequency_and_duration_name_their_denominator(parents):
    frequency = frequency_by(parents)
    assert int(frequency["records"].sum()) == len(parents)
    durations = duration_by(parents)
    assert int(durations["records"].sum()) == len(parents)
    # right = 60 + 180 = 240 s = 4.0 min; left = 120 s = 2.0 min
    assert durations.iloc[0]["minutes"] == pytest.approx(4.0)


def test_sentiment_and_language_counts_are_per_record_not_per_mention(parents):
    sentiments = sentiment_counts(parents).set_index("sentiment")["records"].to_dict()
    assert sentiments == {"positive": 2, "neutral": 1, "negative": 1}
    languages = language_counts(parents).set_index("language")["records"].to_dict()
    assert languages == {"fi": 1, "en": 1, "pl": 1}


def test_child_counts_are_bounded_and_labelled(children):
    themes = child_counts(children, "postprocess_themes")
    assert themes.iloc[0]["label"] == "elections"
    assert int(themes.iloc[0]["videos"]) == 2


def test_child_counts_count_videos_not_mentions():
    """A term said twice in one video is one video mentioning it — the child table has two rows."""
    repeated = pd.DataFrame(
        {
            "source_key": ["k1", "k1", "k2"],
            "field": ["postprocess_themes"] * 3,
            "item.label": ["elections", "elections", "elections"],
        }
    )
    counted = child_counts(repeated, "postprocess_themes")
    assert int(counted.iloc[0]["videos"]) == 2
    assert "records" not in counted.columns


def test_filters_have_a_column_and_unsupported_ones_are_declared():
    for name, column in FILTERS.items():
        assert column, name
    assert set(UNSUPPORTED_FILTERS) == {"ManifestoBERTa class", "LDA topic", "Whisper model-free entity filter"}


def test_children_loader_reads_a_per_country_layout(tmp_path: Path):
    """#263 asks for one layout; until then the loader must not silently read only one of them."""
    country = tmp_path / "finland"
    (country / "children").mkdir(parents=True)
    pd.DataFrame({"child_id": ["c1"], "source_key": ["k1"], "field": ["postprocess_themes"],
                  "item.label": ["elections"]}).to_csv(country / "children" / "themes.csv", index=False)
    loaded = load_children(tmp_path, pd.DataFrame())
    assert list(loaded["item.label"]) == ["elections"]


def test_children_loader_reads_a_flat_layout(tmp_path: Path):
    pd.DataFrame({"child_id": ["c1"], "source_key": ["k1"], "field": ["postprocess_entities"],
                  "item.label": ["Orpo"]}).to_csv(tmp_path / "entities.csv", index=False)
    loaded = load_children(tmp_path, pd.DataFrame())
    assert list(loaded["item.label"]) == ["Orpo"]


def test_children_loader_is_empty_rather_than_raising(tmp_path: Path):
    assert load_children(tmp_path, pd.DataFrame()).empty


def test_the_workbench_view_renders_without_exception(tmp_path: Path, monkeypatch):
    """The claim is about a live view, so it is asserted through Streamlit, not only in the model."""
    pd.DataFrame(
        {
            "country": ["finland"],
            "video_id": ["synthetic"],
            "source_key": ["k1"],
            "political_preference": ["right"],
            "source_type": ["tiktok"],
            "asr_language": ["fi"],
            "video_duration_seconds": [60],
            "timestamp": ["2024-05-01T10:00:00Z"],
            "asr_transcript": ["a transcript"],
            "asr_translation": ["a translation"],
            "ocr_1": ["some ocr"],
            "frame_analysis_1": ["a frame analysis"],
            "summary_analysis": ["a summary"],
            "formula_of_populism_analysis": ["a formula"],
            "positive": [1],
            "neutral": [0],
            "negative": [0],
            "researcher_note": ["looks fine"],
        }
    ).to_csv(tmp_path / "combined.csv", index=False)
    (tmp_path / "children").mkdir()
    pd.DataFrame(
        {
            "child_id": ["c1", "c2"],
            "source_key": ["k1", "k1"],
            "field": ["postprocess_themes", "postprocess_entities"],
            "index": [0, 0],
            "item.label": ["elections", "Orpo"],
        }
    ).to_csv(tmp_path / "children" / "themes.csv", index=False)

    monkeypatch.setenv("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LACLAUGPT_VIS_DEMO_PASSWORD", raising=False)
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "src" / "laclaugpt_visualization" / "ep24_reprocessed_app.py"))
    app.run(timeout=60)
    assert not app.exception

    view = next(radio for radio in app.sidebar.radio if radio.label == "Research view")
    view.set_value("Legacy parity · workbench").run(timeout=60)
    assert not app.exception, app.exception
    # The tabs come from the module's registry, and the record's child-table entities must be rendered.
    assert "Legacy parity · researcher workbench" in [heading.value for heading in app.subheader]


def test_filtered_child_labels_are_scoped_and_deduplicated():
    parents = pd.DataFrame({"source_key": ["a", "b"], "country": ["finland", "poland"]})
    children = pd.DataFrame({
        "source_key": ["a", "a", "b", "missing"],
        "country": ["finland", "finland", "poland", "finland"],
        "field": ["postprocess_themes"] * 4,
        "item.label": ["justice", "justice", "climate", "noise"],
    })
    scoped = scope_children(children, parents.iloc[:1])
    assert list(scoped["item.label"]) == ["justice", "justice"]
    result = child_counts(scoped, "postprocess_themes")
    assert result.to_dict("records") == [{"label": "justice", "records": 1}]


def test_ambiguous_parent_keys_never_multiply_child_counts():
    parents = pd.DataFrame({"source_key": ["same", "same"], "country": ["finland", "finland"]})
    children = pd.DataFrame({"source_key": ["same"], "country": ["finland"],
                             "field": ["postprocess_entities"], "item.label": ["Person"]})
    assert scope_children(children, parents).empty


def test_cross_country_key_collision_requires_country_on_child():
    parents = pd.DataFrame({"source_key": ["same", "same"],
                            "country": ["finland", "poland"]})
    child = pd.DataFrame({"source_key": ["same"], "field": ["postprocess_themes"],
                          "item.label": ["justice"]})
    assert scope_children(child, parents).empty
    child["country"] = "poland"
    assert len(scope_children(child, parents)) == 1


def test_same_native_key_across_countries_keeps_distinct_video_counts():
    parents = pd.DataFrame({"source_key": ["shared", "shared"],
                            "country": ["finland", "poland"]})
    children = pd.DataFrame({"source_key": ["shared", "shared"],
                             "country": ["finland", "poland"],
                             "field": ["postprocess_themes", "postprocess_themes"],
                             "item.label": ["justice", "justice"]})
    scoped = scope_children(children, parents)
    assert child_counts(scoped, "postprocess_themes").iloc[0]["records"] == 2
    assert record_tabs(parents.iloc[0].to_dict(), scoped)["Themes"]["content"] == ["justice"]
