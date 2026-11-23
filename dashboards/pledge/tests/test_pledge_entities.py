"""Entity merging tests for the PLEDGE dashboard.

The rule is corpus-driven: ``build_forms`` learns one surface form per same-meaning key from the
whole column, and ``merge_cell`` folds a cell through it. So each test builds the forms it needs —
that is also what stops the rule from folding words that merely look similar.
"""

from __future__ import annotations

from pledge_entities import build_forms, merge_cell, merge_labels, split_cell


def test_a_cell_splits_into_atomic_tags() -> None:
    assert split_cell("european union, politician") == ["european union", "politician"]
    assert split_cell("political parties; politicians") == ["political parties", "politicians"]
    assert split_cell("nan") == []
    assert split_cell("") == []


def test_the_eu_is_one_entity_however_it_was_tagged() -> None:
    forms = build_forms(["european union"] * 20 + ["eu", "E.U.", "the eu", "european union eu"])
    for spelling in ("eu", "E.U.", "the eu", "european union eu", "european union", "the European Union"):
        assert merge_labels([spelling], forms) == ["european union"], spelling


def test_institutions_are_not_folded_into_the_union() -> None:
    forms = build_forms(["european union", "european commission", "european parliament", "european unity"])
    assert merge_labels(["european union", "european commission", "european parliament", "european unity"], forms) == [
        "european union",
        "european commission",
        "european parliament",
        "european unity",
    ]


def test_a_leading_article_never_survives() -> None:
    """The corpus is lower-case, so a "The"-only rule would miss "the speaker" (197 occurrences)."""
    forms = build_forms(["speaker"] * 5 + ["the speaker"] * 3)
    assert merge_cell("the speaker", forms) == "speaker"


def test_accents_and_word_separators_are_not_meaning() -> None:
    forms = build_forms(["pedro sánchez"] * 10 + ["pedro sanchez", "karacsony_gergely", "karácsony gergely"])
    assert merge_cell("pedro sanchez", forms) == "pedro sánchez"  # the accented spelling wins
    assert merge_cell("karacsony_gergely", forms) == merge_cell("karácsony gergely", forms)


def test_a_qualifying_parenthesis_is_dropped_but_a_different_referent_is_kept() -> None:
    forms = build_forms(["european union"] * 9 + ["european union (eu)", "government", "government (france)"])
    assert merge_cell("european union (eu)", forms) == "european union"
    # "government (france)" names a different government than "government": keep it apart.
    assert merge_cell("government (france)", forms) == "government (france)"


def test_singular_and_plural_are_one_tag_when_both_occur() -> None:
    forms = build_forms(["politician", "politician", "politicians", "politicians", "politicians"])
    assert merge_cell("politician, politicians", forms) == "politicians"


def test_a_word_that_only_looks_plural_is_left_alone() -> None:
    forms = build_forms(["politics", "politics", "politics"])
    assert merge_cell("politics", forms) == "politics"


def test_trailing_party_folds_only_when_the_bare_form_exists() -> None:
    forms = build_forms(["vox"] * 10 + ["vox party"] * 3)
    assert merge_cell("vox party", forms) == "vox"
    forms = build_forms(["green party"] * 3)  # no bare "green" in this corpus
    assert merge_cell("green party", forms) == "green party"


def test_merging_a_cell_dedupes_the_variants_it_folds() -> None:
    forms = build_forms(["european union"] * 5 + ["european union eu"])
    assert merge_cell("european union eu, european union", forms) == "european union"


def test_a_compound_cell_keeps_both_meanings_in_order() -> None:
    forms = build_forms(["european union"] * 5 + ["politician", "politicians", "politicians"])
    assert merge_cell("european union, politician", forms) == "european union, politicians"


def test_matching_is_case_and_whitespace_insensitive() -> None:
    forms = build_forms(["european union"] * 5)
    assert merge_cell("  EUROPEAN   UNION  ,  EU ", forms) == "european union"
