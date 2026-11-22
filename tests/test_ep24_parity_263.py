"""#263 acceptance criterion 5: prove the parity claim mechanically.

For every legacy tab, either a mapped new-data view exists or the tab is declared absent
with the missing source named. These tests are the machine-checkable half of "exactly
like the legacy dashboard" — the half that does not need a browser.
"""

import pandas as pd

from laclaugpt_visualization.ep24_researcher_parity import (
    ABSENT_TABS,
    AGGREGATE_TABS,
    DATE_FIELDS,
    PLATFORM_MAPPING,
    RECORD_TABS,
    absent_tabs,
    aggregate_tab_parity,
    counts,
    denominator_caption,
    identity_rule,
    legacy_tab_names,
    record_tab_parity,
    record_values,
)

#: The columns the reprocessed FI/PL/PT export actually carries (issue §3.1).
EXPORT_COLUMNS = [
    "country", "source_type", "account_type", "political_preference",
    "video_duration_seconds", "video_id", "asr_transcript", "asr_translation",
    "ocr_1", "frame_analysis_1", "vllm_video_analysis", "summary_analysis",
    "summary_summary_md", "formula_of_populism_analysis", "positive", "neutral",
    "negative", "source_language", "language", "postprocess_themes",
    "postprocess_entities", "researcher_note", "created_at",
]


def test_every_legacy_tab_is_accounted_for_exactly_once():
    parity = [*record_tab_parity(EXPORT_COLUMNS), *aggregate_tab_parity(EXPORT_COLUMNS)]
    assert sorted(tab.legacy_tab for tab in parity) == sorted(legacy_tab_names())


def test_record_tabs_map_to_columns_this_export_really_has():
    mapped = {tab.legacy_tab: tab.source for tab in record_tab_parity(EXPORT_COLUMNS)
              if tab.status == "mapped"}
    assert set(mapped) == set(RECORD_TABS), "every per-record legacy tab must be readable"
    for tab, sources in mapped.items():
        assert all(column in EXPORT_COLUMNS for column in sources), tab


def test_aggregate_tabs_are_mapped_except_the_two_with_no_source():
    parity = {tab.legacy_tab: tab for tab in aggregate_tab_parity(EXPORT_COLUMNS)}
    assert set(parity) == {*AGGREGATE_TABS, *ABSENT_TABS}
    assert parity["Topics"].status == "absent" and "lda_topic" in parity["Topics"].reason
    assert parity["ManifestoBERTa"].status == "absent"
    assert "manifestoberta_predicted_class" in parity["ManifestoBERTa"].reason
    for tab in AGGREGATE_TABS:
        assert parity[tab].status == "mapped", tab


def test_absent_tabs_are_listed_with_reasons_never_rendered_empty():
    absent = absent_tabs(EXPORT_COLUMNS)
    assert {tab.legacy_tab for tab in absent} == set(ABSENT_TABS)
    assert all(tab.reason for tab in absent), "an absent tab must say why"


def test_a_tab_with_no_column_is_absent_not_silently_dropped():
    stripped = [column for column in EXPORT_COLUMNS if column != "ocr_1"]
    parity = {tab.legacy_tab: tab for tab in record_tab_parity(stripped)}
    assert parity["OCR (frame 1)"].status == "absent"
    assert "OCR (frame 1)" in {tab.legacy_tab for tab in absent_tabs(stripped)}


def test_counts_name_their_denominator_and_identity_rule():
    frame = pd.DataFrame({"country": ["FI", "FI", "PL", None], "video_id": ["a", "b", "c", "d"]})
    table = counts(frame, "country")
    assert list(table["records"]) == [2, 1, 1]
    assert table.attrs["denominator"].startswith("4 rows")
    assert "video_id" in table.attrs["identity_rule"]
    caption = denominator_caption(table, "country")
    assert "denominator" in caption and "identity" in caption


def test_counts_on_a_missing_column_say_absent_rather_than_drawing_a_chart():
    table = counts(pd.DataFrame({"x": [1]}), "political_preference")
    assert table.empty and table.attrs["denominator"] == "column absent"


def test_identity_rule_admits_when_no_stable_id_exists():
    assert "no stable id" in identity_rule(["country", "asr_transcript"])


def test_platform_is_derived_and_the_derivation_is_stated():
    assert "source_type" in PLATFORM_MAPPING and "account_type" in PLATFORM_MAPPING


def test_the_date_filter_names_a_column_the_export_has():
    assert "created_at" in DATE_FIELDS
    assert set(DATE_FIELDS) & set(EXPORT_COLUMNS), "at least one date field must exist in this export"


def test_record_values_return_only_present_columns():
    row = {"country": "FI", "asr_transcript": "text"}
    assert record_values(row, ["country", "asr_transcript", "ocr_1"]) == row
