"""Legacy-parity analytics (issue #242 §3).

The legacy :8501 dashboard asked aggregate questions. These tests pin the answers the new app gives
from this export, and — more importantly — that an absent field produces no chart rather than a zero
that reads as a finding.
"""
from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.live_steps import (
    country_preference_platform,
    duration_by,
    duration_seconds,
    language_by_preference,
    preference_counts,
)


def frame(**overrides) -> pd.DataFrame:
    base = {
        "record_id": ["fi/1", "fi/2", "pl/1", "pt/1"],
        "country": ["finland", "finland", "poland", "portugal"],
        "political_preference": ["government", "opposition", "government", ""],
        "source_type": ["Instagram", "Tiktok", "Instagram", "Youtube"],
        "video_duration_seconds": ["60", "120", "", "3600"],
        "asr_language": ["fi", "fi", "pl", "pt"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_frequency_counts_every_selected_video_once():
    counts = preference_counts(frame())
    assert int(counts["records"].sum()) == 4
    assert set(counts["preference"]) == {"government", "opposition", "not reported"}


def test_duration_by_group_sums_hours_and_counts_what_it_could_not_use():
    hours = duration_by(frame()).set_index("political_preference")
    assert hours.loc["government", "hours"] == 0.02  # 60 s, the only government row with a duration
    assert hours.loc["government", "records"] == 1
    assert hours.loc["not reported", "hours"] == 1.0  # 3 600 s
    assert int(hours["without_duration"].iloc[0]) == 1


def test_duration_by_returns_nothing_when_the_field_is_absent():
    empty = duration_by(frame().drop(columns=["video_duration_seconds"]))
    assert empty.empty


def test_the_three_way_breakdown_defaults_missing_fields_to_a_label_not_a_crash():
    table = country_preference_platform(frame().drop(columns=["source_type"]))
    assert not table.empty
    assert set(table["source_type"]) == {"not exported"}
    assert int(table["records"].sum()) == 4


def test_the_three_way_breakdown_needs_at_least_two_axes():
    table = country_preference_platform(frame()[["record_id"]])
    assert table.empty


def test_durations_drop_blanks_instead_of_zero_filling():
    values = duration_seconds(frame())
    assert len(values) == 3
    assert 0.0 not in list(values)


def test_language_by_preference_keeps_the_preference_axis():
    table = language_by_preference(frame())
    assert int(table["records"].sum()) == 4
    assert "political_preference" in table.columns


# -- the parity record itself -------------------------------------------------------------------- #

def test_the_parity_record_names_every_legacy_chart_and_its_verdict():
    """The record is the acceptance evidence, so it must actually answer per surface."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[1] / "docs" / "EP24_LEGACY_PARITY_242.md").read_text(encoding="utf-8")
    for legacy in (
        "Recording Frequency by Political Preference",
        "Video Release Timeline",
        "Video Duration Distribution",
        "Total Video Duration by Political Preference",
        "Videos by Country, Political Preference & Source Type",
        "Political Preference Distribution",
        "Dataset Coverage Gauges",
        "Top 20 entities",
        "Top 20 Themes",
        "ManifestoBERTa",
        "Top 30 Persons",
    ):
        assert legacy in doc, f"the parity record does not answer for {legacy!r}"
    assert "not reproduced" in doc, "an unavailable legacy surface must be named, not omitted"


def test_the_app_uses_the_legacy_design_language():
    """#242 asks for the same overall design language, so the palette is part of the contract."""
    from pathlib import Path

    app = (Path(__file__).resolve().parents[1] / "src" / "laclaugpt_visualization"
           / "live_steps_app.py").read_text(encoding="utf-8")
    assert "#6C63FF" in app and "ep24_legacy" in app
    assert "pio.templates.default" in app
