"""The human workbooks decide the name; the corpus decides the count (#311 / #315).

Tomi curated `entities.xlsx`, `persons.xlsx` and `themes.xlsx` by hand. These tests pin the two
properties that make using them safe: a workbook row is taken verbatim (so the `(Party; Country)`
convention survives), and a label the workbook does not know is reported as uncovered rather than
quietly attributed to human work.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import workbooks
from ep24_merge_lab.model import LabelStat


def _write(path: Path, rows: list[tuple[str, str]], sheet: str = "Sheet3") -> Path:
    book = openpyxl.Workbook()
    page = book.active
    page.title = sheet
    page.append(("old", "new"))
    for old, new in rows:
        page.append((old, new))
    book.save(path)
    return path


def test_a_workbook_row_is_taken_verbatim(tmp_path: Path):
    path = _write(tmp_path / "persons.xlsx", [("abir al-sahlani", "Abir Al-Sahlani (Centre Party; Sweden)")])
    table = workbooks.read_workbook(path, "person")
    assert table.canonical("Abir Al-Sahlani") == "Abir Al-Sahlani (Centre Party; Sweden)"
    assert table.covers("  abir   al-sahlani "), "matching is on the string a human typed"
    assert not table.covers("someone else")


def test_the_same_spelling_pointing_at_two_names_is_a_conflict_not_a_coin_flip(tmp_path: Path):
    path = _write(tmp_path / "entities.xlsx", [("cdu", "CDU"), ("CDU", "Christian Democratic Union")])
    table = workbooks.read_workbook(path, "entity")
    assert table.canonical("cdu") == "CDU", "the first row wins; the second is reported"
    assert table.conflicts and "Christian Democratic Union" in table.conflicts["cdu"]


def test_empty_rows_are_counted_not_silently_dropped(tmp_path: Path):
    path = _write(tmp_path / "themes.xlsx", [("activism", "activism"), ("", "orphan")])
    table = workbooks.read_workbook(path, "theme")
    assert table.empty_rows == 1
    assert len(table.pairs) == 1


def test_merging_from_sources_reports_what_the_workbook_did_not_cover(tmp_path: Path):
    path = _write(
        tmp_path / "entities.xlsx",
        [("true finns", "Finns Party"), ("perussuomalaiset", "Finns Party")],
    )
    table = workbooks.read_workbook(path, "entity")
    pooled = {
        "entity": [
            LabelStat(label="True Finns", count=3),
            LabelStat(label="perussuomalaiset", count=4),
            LabelStat(label="Something Else", count=5),
        ]
    }
    merged, coverage = workbooks.merge_from_sources(pooled, {"entity": table})
    clusters = {cluster.canonical: cluster for cluster in merged["entity"]}
    assert clusters["Finns Party"].occurrences == 7
    assert set(clusters["Finns Party"].members) == {"True Finns", "perussuomalaiset"}
    assert clusters["Finns Party"].source == "workbook"
    assert clusters["Something Else"].source == "matcher"
    assert coverage["entity"] == {
        "raw_labels": 3,
        "covered_by_workbook": 2,
        "matcher_only": 1,
        "clusters": 2,
        "workbook_rows": 2,
        "workbook_conflicts": 0,
    }


def test_a_missing_workbook_is_an_error_not_an_empty_merge(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        workbooks.read_workbook(tmp_path / "absent.xlsx", "entity")


def test_occurrences_are_conserved_when_a_workbook_merges(tmp_path: Path):
    path = _write(tmp_path / "themes.xlsx", [("activists", "activism")])
    table = workbooks.read_workbook(path, "theme")
    pooled = {"theme": [LabelStat(label="activists", count=2), LabelStat(label="activism", count=5)]}
    merged, _ = workbooks.merge_from_sources(pooled, {"theme": table})
    assert sum(cluster.occurrences for cluster in merged["theme"]) == 7
