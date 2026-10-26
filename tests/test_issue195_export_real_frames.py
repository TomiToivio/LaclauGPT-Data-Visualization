"""Issue #195 Part 1: the export must survive the *real* cumulative frames.

The merged exporter passed its synthetic tests but aborted on the actual data:

* a cumulative frame repeats one video across successive runs (each carrying more stage output), and
  the exporter raised ``duplicate source identities`` instead of exporting anything;
* the Portuguese rows live in a shared legacy export that also holds Finland, Poland, Sweden, …, and
  the country check raised ``country mismatch`` for every row.

These tests pin the fixes with synthetic frames shaped like the real ones.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ep24.export_demo import export


def _frame(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_a_repeated_identity_keeps_the_most_complete_row(tmp_path: Path) -> None:
    """A later run of the same video carries more stages; that row must be the one exported."""
    finland = _frame(tmp_path / "finland.csv", [
        {"dataset": "ep24", "country": "finland", "video_id": "v1", "source_type": "tiktok",
         "allas_filename": "v1.mp4", "asr_transcript": "early", "summary_analysis": ""},
        {"dataset": "ep24", "country": "finland", "video_id": "v1", "source_type": "tiktok",
         "allas_filename": "v1.mp4", "asr_transcript": "late", "summary_analysis": "full",
         "laclau_status": "ok", "dna_status": "ok"},
    ])
    inputs = {
        "finland": finland,
        "poland": _frame(tmp_path / "poland.csv", [
            {"dataset": "ep24", "country": "poland", "video_id": "p1", "source_type": "tiktok",
             "allas_filename": "p1.mp4", "asr_transcript": "x"}]),
        "portugal": _frame(tmp_path / "portugal.csv", [
            {"dataset": "ep24", "country": "portugal", "video_id": "t1", "source_type": "tiktok",
             "allas_filename": "t1.mp4", "asr_transcript": "y"}]),
    }
    output = tmp_path / "out"
    manifest = export(inputs, output)

    assert manifest["duplicate_rows_merged"] == 1
    assert manifest["by_country"]["finland"] == 1
    rows = list(pd.read_csv(output / "finland.csv", dtype=str, keep_default_na=False).to_dict("records"))
    assert rows[0]["summary_analysis"] == "full", "the most complete run wins, not the first"
    assert rows[0]["laclau_status"] == "ok"


def test_a_shared_source_is_selected_by_country(tmp_path: Path) -> None:
    """One legacy export holding several countries must be filterable, not rejected."""
    shared = _frame(tmp_path / "shared.csv", [
        {"dataset": "ep24", "country": "Portugal", "video_id": "t1", "source_type": "tiktok",
         "allas_filename": "t1.mp4", "summary_analysis": "portugues"},
        {"dataset": "ep24", "country": "Poland", "video_id": "p1", "source_type": "tiktok",
         "allas_filename": "p1.mp4", "summary_analysis": "polski"},
        {"dataset": "ep24", "country": "Sweden", "video_id": "s1", "source_type": "tiktok",
         "allas_filename": "s1.mp4", "summary_analysis": "svenska"},
    ])
    inputs = {
        "finland": _frame(tmp_path / "finland.csv", [
            {"dataset": "ep24", "country": "finland", "video_id": "f1", "source_type": "tiktok",
             "allas_filename": "f1.mp4", "asr_transcript": "z"}]),
        "poland": _frame(tmp_path / "poland.csv", [
            {"dataset": "ep24", "country": "poland", "video_id": "p1", "source_type": "tiktok",
             "allas_filename": "p1.mp4", "asr_transcript": "polski"}]),
        "portugal": shared,
    }
    output = tmp_path / "out"
    manifest = export(inputs, output, selectors={"portugal": "Portugal"})

    assert manifest["by_country"]["portugal"] == 1
    rows = list(pd.read_csv(output / "portugal.csv", dtype=str, keep_default_na=False).to_dict("records"))
    assert [row["summary_analysis"] for row in rows] == ["portugues"]


def test_a_selector_that_matches_nothing_is_an_error(tmp_path: Path) -> None:
    shared = _frame(tmp_path / "shared.csv", [
        {"dataset": "ep24", "country": "Poland", "video_id": "p1", "source_type": "tiktok",
         "allas_filename": "p1.mp4", "summary_analysis": "polski"}])
    inputs = {
        "finland": shared,
        "poland": shared,
        "portugal": _frame(tmp_path / "portugal.csv", [
            {"dataset": "ep24", "country": "portugal", "video_id": "t1", "source_type": "tiktok",
             "allas_filename": "t1.mp4", "asr_transcript": "y"}]),
    }
    with pytest.raises(ValueError, match="no rows for country"):
        export(inputs, tmp_path / "out", selectors={"finland": "Portugal"})


def test_country_mismatch_still_fails_without_a_selector(tmp_path: Path) -> None:
    """Silent merging of two countries must stay impossible."""
    inputs = {
        "finland": _frame(tmp_path / "f.csv", [
            {"dataset": "ep24", "country": "poland", "video_id": "p", "source_type": "tiktok",
             "allas_filename": "p.mp4", "asr_transcript": "x"}]),
        "poland": _frame(tmp_path / "p.csv", [
            {"dataset": "ep24", "country": "poland", "video_id": "p", "source_type": "tiktok",
             "allas_filename": "p.mp4", "asr_transcript": "x"}]),
        "portugal": _frame(tmp_path / "t.csv", [
            {"dataset": "ep24", "country": "portugal", "video_id": "t", "source_type": "tiktok",
             "allas_filename": "t.mp4", "asr_transcript": "x"}]),
    }
    with pytest.raises(ValueError, match="country mismatch"):
        export(inputs, tmp_path / "out")


def test_the_merge_is_reported_not_hidden(tmp_path: Path) -> None:
    finland = _frame(tmp_path / "finland.csv", [
        {"dataset": "ep24", "country": "finland", "video_id": "v", "source_type": "tiktok",
         "allas_filename": "v.mp4", "asr_transcript": "a"},
        {"dataset": "ep24", "country": "finland", "video_id": "v", "source_type": "tiktok",
         "allas_filename": "v.mp4", "asr_transcript": "b"},
        {"dataset": "ep24", "country": "finland", "video_id": "v", "source_type": "tiktok",
         "allas_filename": "v.mp4", "asr_transcript": "c"},
    ])
    inputs = {
        "finland": finland,
        "poland": _frame(tmp_path / "p.csv", [
            {"dataset": "ep24", "country": "poland", "video_id": "p", "source_type": "tiktok",
             "allas_filename": "p.mp4", "asr_transcript": "x"}]),
        "portugal": _frame(tmp_path / "t.csv", [
            {"dataset": "ep24", "country": "portugal", "video_id": "t", "source_type": "tiktok",
             "allas_filename": "t.mp4", "asr_transcript": "x"}]),
    }
    output = tmp_path / "out"
    manifest = export(inputs, output)
    assert manifest["duplicate_rows_merged"] == 2
    assert json.loads((output / "manifest.json").read_text())["duplicate_rows_merged"] == 2
