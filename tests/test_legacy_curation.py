"""Acceptance tests for the legacy EP24 curation CLI (issue #300).

Every test names the criterion it pins: the Orpo example, ambiguous surnames, multilingual
aliases, non-equivalent themes/topics, opposing sentiments, unsafe transitive merges, and manual
decisions surviving a re-run.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from laclaugpt_visualization.legacy_curation import (
    CATEGORIES,
    curate,
    normalise,
    read_labels,
    write_outputs,
)


def _canonical(result: dict, category: str) -> dict[str, str]:
    return {
        row["canonical"]: row["aliases"]
        for row in result["canonical"]  # type: ignore[index]
        if row["category"] == category
    }


def test_the_orpo_example_resolves_to_the_full_name() -> None:
    """'Petteri Orpo', 'Prime Minister Orpo', 'PM Orpo' and 'Orpo' are one person."""
    labels = Counter({
        "Petteri Orpo": 120, "Prime Minister Orpo": 9, "PM Orpo": 7, "Orpo": 34,
    })
    result = curate({"persons": labels})
    assert _canonical(result, "persons")["Petteri Orpo"] == "Petteri Orpo; Orpo; Prime Minister Orpo; PM Orpo"


def test_an_ambiguous_surname_is_queued_not_guessed() -> None:
    """Two people share the surname: 'Kallas' must not be folded into either."""
    labels = Counter({"Kaja Kallas": 40, "Siim Kallas": 12, "Kallas": 6})
    result = curate({"persons": labels})
    assert _canonical(result, "persons") == {}
    review = [row for row in result["review"] if row["category"] == "persons"]  # type: ignore[index]
    assert any("Kallas" in row["candidates"] for row in review)
    assert any(row["method"] == "ambiguous-surname" for row in review)


def test_multilingual_and_abbreviated_aliases_share_a_referent() -> None:
    labels = Counter({"Suomi": 5, "Finland": 90, "EU": 70, "European Union": 300})
    result = curate({"entities": labels})
    canonical = _canonical(result, "entities")
    assert canonical["Finland"] == "Finland; Suomi"
    assert canonical["European Union"] == "European Union; EU"


def test_related_topics_are_not_merged() -> None:
    """"migration" and "migration policy" are related, not the same topic."""
    labels = Counter({"migration": 50, "migration policy": 20, "policy migration": 3})
    result = curate({"topics": labels})
    canonical = _canonical(result, "topics")
    assert "migration" not in canonical  # no merge across the two meanings
    assert canonical["migration policy"] == "migration policy; policy migration"


def test_opposing_sentiments_are_never_merged() -> None:
    labels = Counter({"positive": 40, "good": 9, "negative": 30, "bad": 6, "neutral": 12})
    result = curate({"sentiments": labels})
    canonical = _canonical(result, "sentiments")
    assert canonical["positive"] == "positive; good"
    assert canonical["negative"] == "negative; bad"
    assert set(canonical) == {"positive", "negative"}


def test_a_transitive_chain_is_demoted_to_review() -> None:
    """A≈B and B≈C must not license A≈C: the cluster goes to review instead."""
    from laclaugpt_visualization import legacy_curation as lc

    chain = lc.Candidate(
        canonical="alpha beta",
        aliases=["alpha beta", "beta gamma"],
        confidence=1.0,
        method="token-set-equality",
        counts={"alpha beta": 5, "beta gamma": 3},
    )
    demoted = lc._demote_chains([chain])[0]
    assert demoted.needs_review
    assert "chain" in demoted.method
    assert demoted.confidence <= 0.5


def test_manual_decisions_survive_a_rerun() -> None:
    """A confirmed merge is honoured; an explicit keep-separate is never silently absorbed."""
    labels = Counter({"Kaja Kallas": 40, "Siim Kallas": 12, "Kallas": 6})
    decisions = {"merge": {"Kallas": "Kaja Kallas"}, "keep_separate": ["Siim Kallas"]}
    result = curate({"persons": labels}, decisions=decisions)
    canonical = _canonical(result, "persons")
    assert canonical == {"Kaja Kallas": "Kaja Kallas; Kallas"}  # the merge, not the proposal
    assert "Siim Kallas" not in canonical.values()
    assert all("Siim Kallas" not in aliases for aliases in canonical.values())


def test_a_csv_source_is_read_and_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "export.csv"
    source.write_text('country,persons,topics\nFI,"Petteri Orpo; PM Orpo",migration\n', encoding="utf-8")
    before = source.read_bytes()

    counts = read_labels(source, "persons")
    assert counts == Counter({"Petteri Orpo": 1, "PM Orpo": 1})

    result = curate({"persons": counts})
    write_outputs(result, tmp_path / "out")
    assert source.read_bytes() == before
    assert (tmp_path / "out" / "aliases.csv").exists()
    assert (tmp_path / "out" / "summary.json").exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    result = curate({"persons": Counter({"Petteri Orpo": 5, "Orpo": 2})})
    paths = write_outputs(result, tmp_path / "out", dry_run=True)
    assert paths == {}
    assert not (tmp_path / "out" / "aliases.csv").exists()


def test_normalisation_is_accent_and_title_insensitive() -> None:
    assert normalise("Pedro Sánchez") == normalise("pedro sanchez")
    assert normalise("PM Orpo", drop_titles=True) == "orpo"


def test_every_category_is_curated_without_error() -> None:
    labelled = {
        "persons": Counter({"Petteri Orpo": 3, "Orpo": 1}),
        "entities": Counter({"Finland": 4, "Suomi": 1}),
        "themes": Counter({"climate policy": 2, "policy climate": 1}),
        "topics": Counter({"migration": 2}),
        "sentiments": Counter({"positive": 2, "good": 1}),
    }
    result = curate(labelled)
    assert set(result["stats"]) == set(CATEGORIES)  # type: ignore[arg-type]
    for stats in result["stats"].values():  # type: ignore[union-attr]
        assert stats["distinct_after"] <= stats["labels"]
