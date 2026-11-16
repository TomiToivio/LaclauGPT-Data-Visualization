"""The video id carries the date, so the legacy date filter and timeline work on the reprocessed export (#263).

Measured on the delivered FI/PL/PT export: all 1,500 records carry an id of the shape
`HEPP24-FI-CR-IG-20240521-1027000`, across 28 distinct days (2024-05-20 .. 2024-06-16), while the export's own
`created_at` and `timestamp` columns are empty for every one of them.
"""
from __future__ import annotations

import pandas as pd
import pytest

from laclaugpt_visualization.ep24_legacy_parity import apply_filters
from laclaugpt_visualization.ep24_reprocessed import (
    add_created_at,
    created_at_from_video_id,
    read_records,
)


def test_the_date_is_read_out_of_the_id():
    assert created_at_from_video_id("HEPP24-FI-CR-IG-20240521-1027000") == pd.Timestamp(
        "2024-05-21", tz="UTC")


def test_the_trailing_field_is_not_read_as_a_clock_time():
    """180 distinct trailing values (1010000 .. 4080000); 366 cannot be any HHMMSS. It is a sequence, so the
    derivation stops at the date rather than inventing a time of day."""
    assert created_at_from_video_id("HEPP24-FI-CR-IG-20240527-1090000") == pd.Timestamp("2024-05-27", tz="UTC")
    assert created_at_from_video_id("HEPP24-PL-CR-FB-20240616-4080000") == pd.Timestamp("2024-06-16", tz="UTC")


@pytest.mark.parametrize("bad", ["", None, "nonsense", "HEPP24-FI-CR-IG-20240521", "HEPP24-FI-IG-99999999-1"])
def test_an_id_without_a_date_gives_nat_rather_than_a_guess(bad):
    assert created_at_from_video_id(bad) is None


def test_a_real_created_at_wins_over_the_derivation():
    frame = pd.DataFrame({
        "video_id": ["HEPP24-FI-CR-IG-20240521-1027000", "HEPP24-FI-CR-IG-20240522-1027000"],
        "created_at": ["2024-06-01T00:00:00Z", ""],
    })
    result = add_created_at(frame)
    assert result["created_at"].iloc[0] == pd.Timestamp("2024-06-01", tz="UTC")
    assert result["created_at"].iloc[1] == pd.Timestamp("2024-05-22", tz="UTC")
    assert result.attrs["created_at_derived"] == 1


def test_a_backfilled_export_makes_the_derivation_a_no_op():
    frame = pd.DataFrame({"video_id": ["HEPP24-FI-CR-IG-20240521-1027000"],
                          "created_at": ["2024-05-21T10:27:00Z"]})
    result = add_created_at(frame)
    assert result.attrs["created_at_derived"] == 0
    assert result.attrs["created_at_source"] == "export"


def test_the_loader_delivers_created_at_for_the_per_country_layout(tmp_path):
    """The delivered layout: <root>/<country>/<country>.csv with blank created_at."""
    for country in ("finland", "poland", "portugal"):
        directory = tmp_path / country
        directory.mkdir()
        (directory / f"{country}.csv").write_text(
            "video_id,country,video_duration_seconds\n"
            f"HEPP24-{country[:2].upper()}-CR-IG-20240521-1027000,{country},30\n",
            encoding="utf-8",
        )
    frame = read_records(tmp_path)
    assert len(frame) == 3
    assert frame["created_at"].notna().all()
    assert frame.attrs["created_at_derived"] == 3


def test_the_parity_date_filter_narrows_on_the_derived_dates():
    frame = pd.DataFrame({
        "source_key": ["a", "b"],
        "country": ["finland", "poland"],
        "video_id": ["HEPP24-FI-CR-IG-20240521-1027000", "HEPP24-PL-CR-IG-20240616-1027000"],
    })
    dated = add_created_at(frame)
    kept = apply_filters(dated, dates=(pd.Timestamp("2024-06-01").date(), pd.Timestamp("2024-06-30").date()))
    assert list(kept["source_key"]) == ["b"]
