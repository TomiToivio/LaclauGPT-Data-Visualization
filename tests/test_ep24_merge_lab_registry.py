"""Tests for the shared merge registry (#311).

The registry is the one artifact every pipeline and dashboard depends on, so the tests here are
about the properties that keep it trustworthy: attributable decisions, scoped mappings, explicit
non-merges that survive, deterministic exports, and a version a run can pin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab.registry import (
    HumanReview,
    Registry,
    RegistryEntry,
    RegistryError,
    Scope,
)


def _entry(**overrides) -> RegistryEntry:
    payload = {
        "category": "entity",
        "alias": "sdp social democratic party",
        "canonical": "Social Democratic Party",
        "status": "approved",
        "reviewers": ("agent-a/run-1", "agent-b/run-2", "agent-c/run-3"),
        "evidence": ("https://en.wikipedia.org/wiki/Social_Democratic_Party",),
        "method": "wikidata-sitelink",
    }
    payload.update(overrides)
    return RegistryEntry(**payload)


def _write(path: Path, entries: list[RegistryEntry]) -> Path:
    path.write_text(
        "".join(json.dumps(entry.as_json(), sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )
    return path


def test_a_sound_entry_validates() -> None:
    assert _entry().validate() == []


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"reviewers": ()}, "attributable"),
        ({"evidence": ()}, "no evidence"),
        ({"category": "colour"}, "unknown category"),
        ({"status": "maybe"}, "unknown status"),
        ({"wiki_title": "X", "wiki_url": ""}, "verified URL"),
        ({"status": "keep_separate", "canonical": "Something else"}, "point at itself"),
    ],
)
def test_a_bad_entry_names_its_problem(overrides: dict, needle: str) -> None:
    problems = " ".join(_entry(**overrides).validate())
    assert needle in problems


def test_sentiment_must_state_its_polarity() -> None:
    problems = _entry(category="sentiment", alias="hopeful", canonical="hope").validate()
    assert any("polarity" in problem for problem in problems)


def test_the_registry_reads_back_what_it_wrote(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    assert registry.problems() == []
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party"


def test_a_missing_registry_is_an_error_not_an_empty_mapping(tmp_path: Path) -> None:
    """A pipeline that cannot find the registry must stop, not silently canonicalise nothing."""
    with pytest.raises(RegistryError):
        Registry.load(tmp_path / "absent.jsonl")


def test_a_broken_line_is_reported_with_its_position(tmp_path: Path) -> None:
    good = json.dumps(_entry().as_json(), sort_keys=True)
    path = tmp_path / "registry.jsonl"
    path.write_text(good + "\nnot json\n", encoding="utf-8")
    with pytest.raises(RegistryError) as caught:
        Registry.load(path)
    assert ":2:" in str(caught.value)


def test_alias_matching_is_case_and_space_insensitive(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry(alias="  SDP Social Democratic Party ")])
    registry = Registry.load(path)
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party"


def test_a_scoped_mapping_only_applies_in_its_context(tmp_path: Path) -> None:
    """'The party' is a different party in Finland and in Germany."""
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(alias="the party", canonical="Finns Party", scope=Scope(country="Finland")),
            _entry(alias="the party", canonical="Social Democratic Party of Germany", scope=Scope(country="Germany")),
        ],
    )
    registry = Registry.load(path)
    assert registry.map_label("entity", "the party", country="Finland") == "Finns Party"
    assert registry.map_label("entity", "the party", country="Germany") == "Social Democratic Party of Germany"
    # No context, no guess: the alias stays as it is rather than borrowing another country's party.
    assert registry.map_label("entity", "the party") == "the party"


def test_keep_separate_survives_into_every_later_run(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.jsonl",
        [_entry(alias="le pen", canonical="le pen", status="keep_separate")],
    )
    registry = Registry.load(path)
    assert registry.map_label("person", "le pen") == "le pen"


def test_a_later_revision_wins_and_the_old_one_stays_on_disk(tmp_path: Path) -> None:
    old = _entry(canonical="Social Democratic Party", revision=1)
    new = _entry(canonical="Social Democratic Party (Finland)", revision=2, status="approved")
    path = _write(tmp_path / "registry.jsonl", [old, new])
    registry = Registry.load(path)
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party (Finland)"
    assert len(registry.entries) == 2, "history is append-only; nothing is rewritten"


def test_a_superseded_entry_is_ignored(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(canonical="Wrong", revision=1, status="superseded"),
            _entry(canonical="Right", revision=2),
        ],
    )
    assert Registry.load(path).map_label("entity", "sdp social democratic party") == "Right"


def test_appending_refuses_an_unauthorised_decision(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    with pytest.raises(RegistryError):
        registry.append([_entry(alias="x", canonical="y", reviewers=(), evidence=())])


def test_appending_keeps_the_file_loadable_and_the_version_moving(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    before = registry.version
    registry.append([_entry(alias="true finns", canonical="Finns Party")])
    reloaded = Registry.load(path)
    assert reloaded.version != before
    assert reloaded.map_label("entity", "true finns") == "Finns Party"


def test_the_version_is_stable_for_the_same_content(tmp_path: Path) -> None:
    first = Registry.load(_write(tmp_path / "a.jsonl", [_entry()]))
    second = Registry.load(_write(tmp_path / "b.jsonl", [_entry()]))
    assert first.version == second.version


def test_the_csv_export_is_deterministic(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry(), _entry(alias="true finns", canonical="Finns Party")])
    registry = Registry.load(path)
    first = registry.to_csv(tmp_path / "one.csv").read_bytes()
    second = registry.to_csv(tmp_path / "two.csv").read_bytes()
    assert first == second
    assert b"keep_separate" in first or b"approved" in first


def test_a_proposal_does_not_rewrite_output(tmp_path: Path) -> None:
    """Three reviews make a decision; one review is a proposal and must not reseal the corpus."""
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(
                alias="true finns",
                canonical="Finns Party",
                status="proposed",
                reviewers=("agent-a/run-1",),
            )
        ],
    )
    registry = Registry.load(path)
    assert registry.map_label("entity", "true finns") == "true finns"
    assert registry.latest("entity", "true finns") is not None  # still visible to a reviewer


def test_sentiment_resolution_is_polarity_specific(tmp_path: Path) -> None:
    rows = [
        _entry(category="sentiment", alias="policy", canonical="Policy support", polarity="positive"),
        _entry(category="sentiment", alias="policy", canonical="Policy criticism", polarity="negative"),
    ]
    registry = Registry.load(_write(tmp_path / "registry.jsonl", rows))
    assert registry.map_label("sentiment", "policy", polarity="positive") == "Policy support"
    assert registry.map_label("sentiment", "policy", polarity="negative") == "Policy criticism"
    assert registry.map_label("sentiment", "policy") == "policy"


def test_conflicting_scopes_do_not_guess(tmp_path: Path) -> None:
    rows = [
        _entry(alias="party", canonical="One", scope=Scope(country="FI")),
        _entry(alias="party", canonical="Two", scope=Scope(language="fi")),
    ]
    registry = Registry.load(_write(tmp_path / "registry.jsonl", rows))
    assert registry.map_label("entity", "party", country="FI", language="fi") == "party"


def test_approval_requires_three_distinct_reviewers() -> None:
    assert _entry(reviewers=("a", "a", "b")).validate()


def test_an_alias_with_a_scope_still_counts_as_present(tmp_path: Path) -> None:
    """Looking up a country-scoped decision without a country must not report it as absent."""
    path = _write(
        tmp_path / "registry.jsonl",
        [_entry(alias="Chega party", canonical="Chega (political party)", scope=Scope(country="PT"))],
    )
    registry = Registry.load(path)
    assert registry.has_alias("entity", "Chega party") is True
    assert registry.latest("entity", "Chega party") is None  # no context, no guess


# ------------------------------------------------------------------ human approval (#315)

def _human_entry(**overrides) -> RegistryEntry:
    payload = {
        "category": "person",
        "alias": "javier milei",
        "canonical": "Javier Milei (La Libertad Avanza; Argentina)",
        "status": "approved",
        "reviewers": ("tomi",),
        "evidence": ("persons.xlsx row 412",),
        "method": "human-workbook",
        "approval": "human",
        "human_review": HumanReview(
            reviewer="tomi",
            at="2026-11-24T20:10:00+00:00",
            snapshot="4d5d6f37e1e0",
            session="merge-lab/7f3c2a",
        ),
    }
    payload.update(overrides)
    return RegistryEntry(**payload)


def test_one_attested_human_reviewer_may_approve_a_mapping() -> None:
    """Owner instruction 2026-11-24: one attributable human settles a mapping, no three AI votes."""
    assert _human_entry().validate() == []


def test_a_human_approval_without_an_attested_session_is_rejected() -> None:
    problems = _human_entry(human_review=HumanReview(reviewer="tomi")).validate()
    assert any("trusted review session" in problem for problem in problems)
    assert any("frozen snapshot" in problem for problem in problems)


def test_a_human_approval_must_name_a_recorded_reviewer() -> None:
    problems = _human_entry(reviewers=("agent-a",)).validate()
    assert any("must appear among the recorded reviewers" in problem for problem in problems)


def test_one_ai_reviewer_still_may_not_approve() -> None:
    """The human path must not become a loophole for a single model vote."""
    problems = _entry(reviewers=("agent-a/run-1",)).validate()
    assert any("three distinct reviewer IDs" in problem for problem in problems)


def test_three_reviewer_unanimity_is_still_the_ai_rule() -> None:
    assert _entry().validate() == []
    assert _entry().approval == ""


def test_an_unattested_human_session_does_not_rewrite_labels(tmp_path: Path) -> None:
    from ep24_merge_lab.registry import HumanReview as Review

    entry = _human_entry()
    path = _write(tmp_path / "registry.jsonl", [entry])
    registry = Registry.load(path)
    assert registry.map_label("person", "javier milei") == "javier milei"
    assert registry.map_label("person", "javier milei", trusted={}) == "javier milei"
    assert registry.map_label(
        "person", "javier milei", trusted={"merge-lab/7f3c2a": "tomi"}
    ) == "Javier Milei (La Libertad Avanza; Argentina)"
    # A session that authenticated somebody else is not attestation for this reviewer.
    assert registry.map_label(
        "person", "javier milei", trusted={"merge-lab/7f3c2a": "agent-x"}
    ) == "javier milei"
    assert registry.unattested_human_approvals({"merge-lab/7f3c2a": "agent-x"})

    # A record that fails validation cannot be loaded at all; if one is loaded unvalidated, an
    # unattested session still must not rewrite a label.
    bad = _human_entry(human_review=Review(reviewer="tomi", session="forged"))
    bad_path = _write(tmp_path / "bad.jsonl", [bad])
    lenient = Registry.load(bad_path, validate=False)
    assert lenient.map_label("person", "javier milei", trusted={"merge-lab/7f3c2a": "tomi"}) == "javier milei"
    assert lenient.unattested_human_approvals({"merge-lab/7f3c2a": "tomi"})
