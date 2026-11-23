"""Label folding: same referent, one surface form (#426 follow-up).

The dashboard counted "EU" (23) and "European Union" (61) as separate actors, splitting a
signifier in two. These tests pin the two halves of that rule: the variants that must fold, and
the near-neighbours that must not.
"""

from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.label_aliases import (
    canonical_forms,
    canonical_label,
    canonicalize_frame,
)


def test_acronym_folds_into_its_expansion():
    forms = canonical_forms(["EU", "European Union"])
    assert canonical_label("EU", forms) == "European Union"
    assert canonical_label("E.U.", forms) == "European Union"


def test_the_commission_is_not_the_union():
    """Over-merging would delete a real institutional distinction."""
    forms = canonical_forms(["EU", "European Union", "European Commission", "EU Commission"])
    assert canonical_label("EU Commission", forms) == "European Commission"
    assert canonical_label("European Union", forms) == "European Union"
    assert canonical_label("European Commission", forms) == "European Commission"


def test_case_variants_resolve_to_one_surface_form():
    forms = canonical_forms(["Safety", "safety", "SAFETY", "Safety"])
    assert canonical_label("safety", forms) == canonical_label("Safety", forms)
    assert canonical_label("SAFETY", forms) == "Safety"


def test_a_leading_article_is_not_a_different_entity():
    forms = canonical_forms(["The Guardian", "Guardian", "Guardian"])
    assert canonical_label("The Guardian", forms) == "Guardian"


def test_a_lowercase_common_noun_keeps_its_article():
    """``the system`` is not ``system``: there the article is part of the phrase (fixture #426)."""
    forms = canonical_forms(["the system", "the system"])
    assert canonical_label("the system", forms) == "the system"


def test_unknown_labels_keep_their_wording():
    """Nothing here may normalise a distinction away speculatively."""
    forms = canonical_forms(["The Unchecked State", "The Surveillance State"])
    assert canonical_label("The Unchecked State", forms) == "Unchecked State"
    assert canonical_label("The Surveillance State", forms) == "Surveillance State"


def test_folding_is_idempotent():
    forms = canonical_forms(["EU", "European Union", "safety", "Safety"])
    once = [canonical_label(label, forms) for label in ("EU", "safety", "Safety")]
    twice = [canonical_label(label, forms) for label in once]
    assert once == twice


def test_frame_folding_merges_counts_and_dedupes_within_a_record():
    frame = pd.DataFrame(
        {
            "entities": [["EU"], ["European Union"], ["EU", "European Union"], ["Open AI"]],
            "signifiers": [["safety"], ["Safety"], [], ["Safety"]],
        }
    )
    folded = canonicalize_frame(frame)

    assert folded["entities"].tolist() == [
        ["European Union"],
        ["European Union"],
        ["European Union"],  # folded to one label, not listed twice
        ["OpenAI"],
    ]
    assert folded["signifiers"].tolist() == [["Safety"], ["Safety"], [], ["Safety"]]
    assert folded.attrs["label_aliases"], "the folding map must be kept for audit"


def test_frame_folding_leaves_non_label_members_alone():
    """``entity_mentions`` can hold dicts; those are not labels and must pass through."""
    mention = {"label": "EU", "span": [0, 2]}
    frame = pd.DataFrame({"entities": [["EU"]], "entity_mentions": [[mention]]})
    folded = canonicalize_frame(frame)
    assert folded["entity_mentions"].tolist() == [[mention]]
    assert folded["entities"].tolist() == [["European Union"]]


def test_frame_folding_never_mutates_the_input():
    frame = pd.DataFrame({"entities": [["EU"]]})
    canonicalize_frame(frame)
    assert frame["entities"].tolist() == [["EU"]]
