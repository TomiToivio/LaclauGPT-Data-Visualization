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
        ("perussuomalaisten finns party", "true finns"),
        ("perussuomalainen party", "true finns"),
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
        # the party's youth wing and a phrase about its campaigning are not the party
        "perussuomalainen nuoriso",
        "perussuomalaiset's tiktok strategy",
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


# ------------------------------------------------------------------ merging within a vocabulary

def test_variant_merges_use_the_example_the_owner_gave() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    labels = {"fidesz": 185, "fidesz party": 115}
    assert variant_merges(labels) == {"fidesz party": "fidesz"}


def test_a_party_without_a_bare_label_is_left_alone() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    assert variant_merges({"green party": 4}) == {}


def test_case_punctuation_and_quotes_are_one_label() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    mapping = variant_merges({'"people"': 1, "people": 12, "nationalism vs. europe": 3,
                              "nationalism vs europe": 9})
    assert mapping['"people"'] == "people"
    assert mapping["nationalism vs. europe"] == "nationalism vs europe"
    # a bracket is part of the label: this is not a spelling variant of the bracketed form
    assert "socialist party (psoe)" not in variant_merges({"socialist party (psoe)": 3, "socialist party psoe": 1})


def test_a_generic_bracket_is_dropped_but_a_name_in_brackets_is_not() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    mapping = variant_merges({"vox": 10, "vox (party)": 2, "vox (political party)": 1,
                              "psoe (spanish socialist workers' party)": 3})
    assert mapping["vox (party)"] == "vox"
    assert mapping["vox (political party)"] == "vox"
    assert "psoe (spanish socialist workers' party)" not in mapping


def test_rights_is_not_right() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    assert variant_merges({"right": 9, "rights": 4}) == {}


def test_a_generic_base_is_not_a_party_name() -> None:
    from ep24_merge_lab.label_cleanup import variant_merges

    mapping = variant_merges({"political": 40, "political party": 31, "political parties": 295,
                              "opposition": 8, "opposition parties": 7, "far-right": 9,
                              "far-right parties": 17})
    assert mapping == {}
