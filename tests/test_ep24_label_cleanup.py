"""Cleanup removes redundancy and never a distinction (#311 owner instruction)."""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab.label_cleanup import clean_cell, clean_label


@pytest.mark.parametrize(
    "raw,expected",
    [
        # the owner's own examples
        ("perussuomalaiset (ps)", "true finns"),
        ("european union (eu)", "european union"),
        # the served data writes the same party with a translated gloss, or in English already
        ("perussuomalaiset (finns party)", "true finns"),
        ("true finns", "true finns"),
        ("the finns party", "true finns"),
        # an acronym of the label is redundant, in either case
        ("partido popular (pp)", "partido popular"),
        ("European People's Party (EPP)", "European People's Party"),
        # a leading English article is not part of the name
        ("the european union", "european union"),
        # an article is not a word of the name, so the acronym still matches
        ("the european union (eu)", "european union"),
        ("perussuomalaisten (ps)", "true finns"),
        # an annotation is not part of the name either
        ("social media platforms (implicit)", "social media platforms"),
    ],
)
def test_redundancy_is_removed(raw: str, expected: str) -> None:
    assert clean_label(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # a disambiguating bracket is the meaning, not noise
        "national politics (finland)",
        "separatism (catalonia)",
        "regional governments (catalonia, basque country)",
        "speaker (self)",
        "candidate/supporter",
        "sánchez (pedro sánchez)",
    ],
)
def test_a_disambiguator_is_never_dropped(raw: str) -> None:
    assert clean_label(raw) in {raw, raw.replace(" (self)", "")}


def test_cell_cleanup_preserves_order_and_collapses_only_new_duplicates() -> None:
    cell = "european union (eu), the european union, eu policies, european union"
    assert clean_cell(cell) == "european union, eu policies"


def test_cell_cleanup_keeps_an_empty_cell_empty() -> None:
    assert clean_cell("") == ""
    assert clean_cell(" , ") == ""


def test_cell_cleanup_honours_the_separator_it_is_given() -> None:
    assert clean_cell("perussuomalaiset (ps); true finns", ";") == "true finns"
