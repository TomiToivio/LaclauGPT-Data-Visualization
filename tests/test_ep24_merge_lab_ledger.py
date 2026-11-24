"""Tests for the review ledger and adjudication (#311).

The issue's hardest requirement is not merging labels — it is proving that *three distinct reviewers*
looked at *the same snapshot* and that disagreement was preserved instead of averaged. These tests
pin that, plus the failure modes that would let a claim of completeness pass without the substance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab.ledger import Ledger, LedgerError, Review

_ROOT = ROOT
SNAPSHOT = "2faa92812dc8a21a" + "0" * 48


def _review(**overrides) -> Review:
    payload = {
        "batch_id": "batch-0001",
        "label_id": "entity:true finns",
        "category": "entity",
        "label": "true finns",
        "reviewer": "reviewer-a/run-1",
        "decision": "merge",
        "canonical": "Finns Party",
        "wiki_title": "Finns Party",
        "wiki_url": "https://en.wikipedia.org/wiki/Finns_Party",
        "wikidata_qid": "Q634277",
        "evidence": ("The party renamed itself in English to Finns Party",),
        "confidence": 0.95,
        "snapshot_sha256": SNAPSHOT,
    }
    payload.update(overrides)
    return Review(**payload)


def _ledger(path: Path, reviews: list[Review]) -> Ledger:
    ledger = Ledger()
    ledger.append(reviews, path)
    return Ledger.load(path)


def _three(reviewer_suffix: str = "", **overrides) -> list[Review]:
    return [_review(reviewer=f"reviewer-{name}{reviewer_suffix}/run", **overrides) for name in "abc"]


# ------------------------------------------------------------------ attribution

def test_an_unattributed_review_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="reviewer is empty"):
        _ledger(tmp_path / "l.jsonl", [_review(reviewer="")])


def test_a_merge_without_a_citation_or_reason_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="verified URL"):
        _ledger(tmp_path / "l.jsonl", [_review(reviewer="a/run", wiki_url="", wiki_title="")])


def test_a_review_without_a_snapshot_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="snapshot"):
        _ledger(tmp_path / "l.jsonl", [_review(reviewer="a", snapshot_sha256="")])


# ------------------------------------------------------------------ coverage

def test_coverage_counts_distinct_reviewers_not_lines(tmp_path: Path) -> None:
    """One reviewer writing twice must not look like two independent voices."""
    ledger = _ledger(
        tmp_path / "l.jsonl",
        [_review(reviewer="reviewer-a/run-1"), _review(reviewer="reviewer-a/run-1", canonical="Finns Party")],
    )
    assert ledger.coverage()["entity:true finns"]["review_count"] == 1
    assert ledger.blocked_labels() == ["entity:true finns"]


def test_a_reviewer_may_revise_and_only_the_revision_counts(tmp_path: Path) -> None:
    ledger = _ledger(
        tmp_path / "l.jsonl",
        [
            _review(reviewer="reviewer-a/run", decision="keep_separate", canonical=""),
            _review(reviewer="reviewer-a/run", decision="merge"),
        ],
    )
    slot = ledger.coverage()["entity:true finns"]
    assert slot["review_count"] == 1
    assert slot["decisions"]["reviewer-a/run"] == "merge"


def test_mixed_snapshots_block_the_label(tmp_path: Path) -> None:
    """Three reviews of three different inputs measure nothing."""
    ledger = _ledger(
        tmp_path / "l.jsonl",
        [
            _review(reviewer="a/run", snapshot_sha256=SNAPSHOT),
            _review(reviewer="b/run", snapshot_sha256="deadbeef" * 8),
            _review(reviewer="c/run", snapshot_sha256=SNAPSHOT),
        ],
    )
    assert ledger.blocked_labels() == ["entity:true finns"]
    assert "different snapshots" in json.dumps(ledger.adjudicate().incomplete)


def test_the_matrix_reports_progress_per_category(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "l.jsonl", _three())
    matrix = ledger.coverage_matrix()
    assert matrix["labels_seen"] == 1
    assert matrix["by_category"]["entity"] == {"labels": 1, "complete": 1}
    assert matrix["short_of_three"] == []


# ------------------------------------------------------------------ adjudication

def test_unanimous_merges_become_an_approved_entry_with_three_reviewers(tmp_path: Path) -> None:
    result = _ledger(tmp_path / "l.jsonl", _three()).adjudicate()
    assert len(result.approved) == 1
    entry = result.approved[0]
    assert entry.canonical == "Finns Party"
    assert entry.status == "approved"
    assert len(entry.reviewers) == 3
    assert _ledger(tmp_path / "l.jsonl", _three()).blocked_labels() == []


def test_unanimous_keep_separate_becomes_a_keep_separate_entry(tmp_path: Path) -> None:
    reviews = [
        _review(reviewer=f"{name}/run", decision="keep_separate", canonical="", wiki_title="", wiki_url="")
        for name in "abc"
    ]
    result = _ledger(tmp_path / "l.jsonl", reviews).adjudicate()
    assert len(result.keep_separate) == 1
    assert result.keep_separate[0].canonical == "true finns"
    assert result.keep_separate[0].status == "keep_separate"


def test_a_split_decision_is_a_conflict_not_a_majority(tmp_path: Path) -> None:
    """2-to-1 is exactly where a wrong canonical would overwrite a dissenting reviewer."""
    reviews = _three()[:2] + [_review(reviewer="c/run", decision="keep_separate", canonical="")]
    result = _ledger(tmp_path / "l.jsonl", reviews).adjudicate()
    assert result.approved == []
    assert len(result.conflicts) == 1
    votes = {vote["reviewer"]: vote["decision"] for vote in result.conflicts[0]["votes"]}
    assert votes == {"reviewer-a/run": "merge", "reviewer-b/run": "merge", "c/run": "keep_separate"}


def test_two_reviews_are_not_enough_and_say_so(tmp_path: Path) -> None:
    result = _ledger(tmp_path / "l.jsonl", _three()[:2]).adjudicate()
    assert result.approved == []
    assert "2 of 3" in result.incomplete[0]["reason"]


def test_agreeing_to_merge_but_naming_different_canonicals_is_a_conflict(tmp_path: Path) -> None:
    """Same intent, different titles is not a settled decision: the issue asks for the exact title."""
    reviews = _three()
    bad = [_review(reviewer="c/run", canonical="True Finns")]
    result = _ledger(tmp_path / "l.jsonl", reviews[:2] + bad).adjudicate()
    assert result.approved == []
    assert result.conflicts[0]["canonicals"] == ["Finns Party", "True Finns"]
    assert "different canonicals" in result.conflicts[0]["reason"]


def test_the_same_canonical_in_different_case_is_not_a_conflict(tmp_path: Path) -> None:
    reviews = _three()
    mixed = [_review(reviewer="c/run", canonical="finns party")]
    result = _ledger(tmp_path / "l.jsonl", reviews[:2] + mixed).adjudicate()
    assert len(result.approved) == 1 and result.conflicts == []


def test_appending_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    ledger = _ledger(path, _three())
    before = path.read_text(encoding="utf-8").count("\n")
    ledger.append([_review(reviewer="d/run")], path)
    assert path.read_text(encoding="utf-8").count("\n") == before + 1


def test_a_corrupt_ledger_names_the_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    path.write_text(json.dumps(_review().as_json()) + "\n{broken\n", encoding="utf-8")
    with pytest.raises(LedgerError, match=":2:"):
        Ledger.load(path)


def test_a_settled_decision_supersedesA_proposal_but_never_another_decision(tmp_path: Path) -> None:
    import sys as _sys

    _sys.path.insert(0, str(_ROOT / "tools"))
    import record_reviews as rr

    ledger_path = tmp_path / "ledger.jsonl"
    registry_path = tmp_path / "registry.jsonl"
    ledger = Ledger()
    ledger.append([_review(reviewer=f"{name}/run") for name in "abc"], ledger_path)

    from ep24_merge_lab.registry import Registry, RegistryEntry
    Registry(entries=[RegistryEntry(
        category="entity", alias="true finns", canonical="Finns Party",
        status="proposed", reviewers=("someone/single-pass",), evidence=("proposal",),
    )]).append(_entries := [RegistryEntry(
        category="entity", alias="true finns", canonical="Finns Party",
        status="proposed", reviewers=("someone/single-pass",), evidence=("proposal",),
    )], registry_path)

    rr.main(["adjudicate", "--ledger", str(ledger_path), "--registry", str(registry_path), "--min-reviews", "3"])
    after = Registry.load(registry_path)
    assert after.latest("entity", "true finns").status == "approved"

    # A second adjudication must not append a duplicate approval.
    before = registry_path.read_text(encoding="utf-8").count("\n")
    rr.main(["adjudicate", "--ledger", str(ledger_path), "--registry", str(registry_path), "--min-reviews", "3"])
    assert registry_path.read_text(encoding="utf-8").count("\n") == before


def test_a_sentiment_decision_covers_every_polarity(tmp_path: Path) -> None:
    """Reviewers judge the target, not the polarity, so the record must say "*" and not be rejected."""
    reviews = [
        _review(
            reviewer=f"{name}/run",
            label_id="sentiment:european union",
            category="sentiment",
            label="european union",
            canonical="European Union",
        )
        for name in "abc"
    ]
    result = _ledger(tmp_path / "l.jsonl", reviews).adjudicate()
    assert result.approved[0].polarity == "*"


# ------------------------------------------------------------------ human decisions (#315)

def _human_review(label_id: str, *, reviewer: str = "tomi", session: str = "merge-lab/7f3c2a",
                  decision: str = "merge", canonical: str = "European Union") -> object:
    return Review(
        batch_id="batch-01",
        label_id=label_id,
        category="sentiment",
        label="european union",
        reviewer=reviewer,
        decision=decision,
        canonical=canonical,
        wiki_url="https://en.wikipedia.org/wiki/European_Union",
        wiki_title="European Union",
        polarity="positive",
        evidence=("https://en.wikipedia.org/wiki/European_Union",),
        confidence=1.0,
        snapshot_sha256="e5c7c6ffed78",
        created_at="2026-11-24T20:10:00+00:00",
        kind="human",
        attested_session=session,
    )


def test_one_attested_human_decision_settles_a_label_alone(tmp_path: Path) -> None:
    """Owner instruction 2026-11-24: no three AI votes are required for a human decision."""
    book = _ledger(tmp_path / "l.jsonl", [_human_review("sentiment:eu|positive")])
    result = book.adjudicate(trusted={"merge-lab/7f3c2a": "tomi"})
    assert [entry.canonical for entry in result.approved] == ["European Union"]
    entry = result.approved[0]
    assert entry.approval == "human"
    assert entry.human_review.session == "merge-lab/7f3c2a"
    assert entry.validate() == []
    assert not result.incomplete


def test_a_human_decision_without_an_attested_session_is_not_applied(tmp_path: Path) -> None:
    book = _ledger(tmp_path / "l.jsonl", [_human_review("sentiment:eu|positive", session="forged")])
    result = book.adjudicate(trusted={"merge-lab/7f3c2a": "tomi"})
    assert not result.approved
    assert any("attested" in item["reason"] for item in result.incomplete)


def test_one_ai_vote_is_still_not_enough(tmp_path: Path) -> None:
    review = _human_review("sentiment:eu|positive")
    review = Review(**{**review.as_json(), "kind": "ai", "attested_session": ""})
    book = _ledger(tmp_path / "l.jsonl", [review])
    result = book.adjudicate(trusted={"merge-lab/7f3c2a": "tomi"})
    assert not result.approved
    assert any("required reviews" in item["reason"] for item in result.incomplete)
