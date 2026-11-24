"""The review panel must be attributable, resumable and honest about what it does not know (#311).

No network here: the model clients and Wikipedia are exercised through their validators, and the
orchestration is tested with plain dictionaries. What matters is the bookkeeping — an opinion that
did not happen must not be counted, and a disagreement must not be averaged into a decision.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab.review import (
    inventory,
    ledger,
    providers,
    reconcile,
    release,
)


def _unit(unit_id: str = "u1", category: str = "person") -> dict:
    return {
        "unit_id": unit_id,
        "category": category,
        "kind": "cluster",
        "labels": ["Petteri Orpo", "Orpo"],
        "canonical": "Petteri Orpo",
        "occurrences": 241,
        "confidence": 0.93,
        "method": "surname",
        "countries": ["finland"],
        "alternatives": [],
        "reason": "",
    }


def _review(reviewer: str, decision: str = "merge", canonical: str = "Petteri Orpo") -> dict:
    return {
        "reviewer": reviewer,
        "model": f"model-{reviewer}",
        "decision": decision,
        "canonical": canonical,
        "wikipedia_title": canonical,
        "confidence": 0.9,
        "rationale": "the corpus uses both spellings for one person",
    }


# ------------------------------------------------------------------ inventory


def test_units_are_identified_by_their_content(tmp_path: Path):
    run = tmp_path / "runs" / "20260101T000000Z"
    run.mkdir(parents=True)
    (run / "canonical_person.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n"
        'Petteri Orpo,"Orpo | Petteri Orpo",2,241,0.930,surname\n',
        encoding="utf-8",
    )
    (run / "review_person.csv").write_text(
        "label,occurrences,alternatives,reason\nMatti Orpo,2,\"Petteri Orpo (0.760)\",near miss\n",
        encoding="utf-8",
    )
    units = inventory.units_from_run(run)
    assert {unit.kind for unit in units} == {"cluster", "candidate"}
    assert len({unit.unit_id for unit in units}) == 2

    # The same labels produce the same id, wherever the run lives.
    again = inventory.units_from_run(run)
    assert [unit.unit_id for unit in units] == [unit.unit_id for unit in again]


def test_freezing_records_a_digest_and_round_trips(tmp_path: Path):
    units = [inventory.DecisionUnit(**_unit())]
    header = inventory.freeze(tmp_path / "run", tmp_path / "inv.json", units)
    assert header["total"] == 1 and len(header["digest"]) == 64
    loaded_header, loaded_units = inventory.load_inventory(tmp_path / "inv.json")
    assert loaded_header["digest"] == header["digest"]
    assert loaded_units[0].unit_id == "u1"


# ------------------------------------------------------------------ ledger


def test_the_ledger_is_append_only_and_resumable(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {"type": "review", "unit_id": "u1", "reviewer": "A", **_review("A")})
    ledger.append(path, {"type": "review", "unit_id": "u1", "reviewer": "B", **_review("B")})
    ledger.append(path, {"type": "attempt", "unit_id": "u1", "reviewer": "C", "error": "timeout"})

    assert ledger.reviewed_pairs(path) == {("u1", "A"), ("u1", "B")}
    coverage = ledger.coverage(path, [_unit()], required=3)
    assert coverage["partial"] == 1 and coverage["complete"] == 0
    assert coverage["per_reviewer"] == {"A": 1, "B": 1}
    assert coverage["failed_attempts"] == 1, "a failure is counted as a failure, not a review"


def test_a_torn_final_line_does_not_cost_the_ledger(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {"type": "review", "unit_id": "u1", "reviewer": "A", **_review("A")})
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "review", "unit_id": "u2", "rev')
    assert len(ledger.reviewed_pairs(path)) == 1


# ------------------------------------------------------------------ reconciliation


def test_three_agreeing_reviewers_approve_automatically():
    approved, queue = reconcile.decide(
        [_unit("u1")],
        {"u1": [_review("A"), _review("B"), _review("C")]},
        required=3,
    )
    assert len(approved) == 1 and not queue
    assert approved[0]["method"] == "unanimous"


def test_two_of_three_queues_and_keeps_the_disagreement_on_record():
    approved, queue = reconcile.decide(
        [_unit()],
        {"u1": [_review("A"), _review("B"), _review("C", decision="keep", canonical="Orpo")]},
        required=3,
    )
    assert not approved and len(queue) == 1
    assert len(queue[0]["reviews"]) == 3


def test_three_way_disagreement_goes_to_a_human():
    approved, queue = reconcile.decide(
        [_unit()],
        {"u1": [_review("A"), _review("B", decision="keep"), _review("C", decision="split")]},
        required=3,
    )
    assert not approved
    assert queue and "no consensus" in queue[0]["reason"]


def test_a_unit_with_two_reviews_is_not_complete():
    approved, queue = reconcile.decide([_unit()], {"u1": [_review("A"), _review("B")]}, required=3)
    assert not approved
    assert "only 2 of 3" in queue[0]["reason"]


def test_adjudication_is_retained_without_automatic_approval():
    approved, queue = reconcile.decide(
        [_unit()],
        {"u1": [_review("A"), _review("B"), _review("C", decision="keep", canonical="Orpo")]},
    )
    verdict = {"decision": "keep", "canonical": "Orpo", "rationale": "two different Orpos"}
    reconcile.attach_adjudications(queue, {"u1": verdict})
    assert not approved
    assert queue[0]["adjudication_proposal"] == verdict


def test_two_reviewers_never_satisfy_unanimity():
    assert not reconcile.unanimous([_review("A"), _review("B")])
    approved, queue = reconcile.decide(
        [_unit()], {"u1": [_review("A"), _review("B")]}, required=2
    )
    assert not approved and queue


def test_three_different_canonicals_never_approve():
    approved, queue = reconcile.decide(
        [_unit()], {"u1": [_review("A"), _review("B", canonical="X"), _review("C", canonical="Y")]}
    )
    assert not approved and len(queue[0]["reviews"]) == 3


def test_failed_attempt_does_not_count():
    approved, queue = reconcile.decide(
        [_unit()], {"u1": [_review("A"), _review("B"), {"reviewer": "C", "type": "attempt"}]}
    )
    assert not approved and "only 2 of 3" in queue[0]["reason"]


def test_unanimous_keep_does_not_export_a_merge():
    approved, queue = reconcile.decide(
        [_unit()], {"u1": [_review(name, decision="keep") for name in "ABC"]}
    )
    assert not approved and queue


# ------------------------------------------------------------------ model output is not trusted


def test_a_review_must_match_the_agreed_schema():
    with pytest.raises(ValueError, match="decision"):
        providers._validate({"decision": "maybe", "canonical": "X"})
    with pytest.raises(ValueError, match="canonical"):
        providers._validate({"decision": "merge", "canonical": " "})
    with pytest.raises(ValueError, match="confidence"):
        providers._validate({"decision": "merge", "canonical": "X", "confidence": 3})
    ok = providers._validate(
        {"decision": "merge", "canonical": "X", "wikipedia_title": "X", "confidence": 0.8}
    )
    assert ok["decision"] == "merge" and ok["wikipedia_title"] == "X"


def test_json_is_recovered_from_a_fenced_reply():
    payload = providers._first_json('```json\n{"decision": "keep", "canonical": "Y"}\n```')
    assert payload["decision"] == "keep"


# ------------------------------------------------------------------ release


def test_a_release_carries_a_registry_and_a_manifest(tmp_path: Path):
    approved = [
        {
            **_unit(),
            "status": "approved",
            "method": "unanimous",
            "decision": "merge",
            "wikipedia_title": "Petteri Orpo",
            "qid": "Q123",
            "rationale": "one person",
            "reviews": [_review(name) for name in "ABC"],
        }
    ]
    path = release.build(
        tmp_path,
        approved=approved,
        human_queue=[{"unit_id": "u2", "category": "person", "reason": "tie"}],
        coverage={"complete": 1},
        inventory_header={"digest": "abc", "base_run": "run", "total": 2},
        reviews_path=tmp_path / "missing.jsonl",
        reviewer_models={"A": "model-a"},
    )
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["frozen_inventory"]["digest"] == "abc"
    assert manifest["units"] == {"frozen": 2, "approved": 1, "human_queue": 1}
    assert manifest["files"]["registry.jsonl"]["sha256"]
    assert (tmp_path / "LATEST_RELEASE").read_text(encoding="utf-8").strip() == path.name

    registry = [json.loads(line) for line in (path / "registry.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["alias"] for row in registry} == {"Petteri Orpo", "Orpo"}
    assert all(row["canonical"] == "Petteri Orpo" for row in registry)
    assert registry[0]["wikipedia_url"].startswith("https://en.wikipedia.org/wiki/")


# ------------------------------------------------------------------ one contract, two writers (#315)


def _shared_problems(result: dict, snapshot: str = "abc123"):
    from ep24_merge_lab.review.runner import shared_problems

    return shared_problems(_unit(), result, snapshot)


def test_a_review_without_the_snapshot_hash_is_not_evidence():
    result = {
        "reviewer": "A", "decision": "merge", "canonical": "Petteri Orpo",
        "wikipedia_title": "Petteri Orpo", "wikipedia_url": "https://en.wikipedia.org/wiki/x",
        "confidence": 0.9, "rationale": "same person",
    }
    assert any("snapshot" in problem for problem in _shared_problems(result, snapshot=""))


def test_a_merge_must_cite_a_url_or_say_why_there_is_none():
    result = {
        "reviewer": "A", "decision": "merge", "canonical": "Some concept",
        "wikipedia_title": None, "wikipedia_url": "", "fallback_reason": "",
        "confidence": 0.9, "rationale": "same concept",
    }
    problems = _shared_problems(result)
    assert any("verified URL" in problem for problem in problems), problems


def test_a_well_formed_review_passes_the_shared_contract():
    result = {
        "reviewer": "A", "decision": "merge", "canonical": "Petteri Orpo",
        "wikipedia_title": "Petteri Orpo", "wikipedia_url": "https://en.wikipedia.org/wiki/Petteri_Orpo",
        "confidence": 0.9, "rationale": "same person",
    }
    assert _shared_problems(result) == []


def test_both_ledgers_refuse_two_reviewers_and_a_bare_majority():
    """The shared ledger and the panel must agree, or the repository has two rules again."""
    from ep24_merge_lab import ledger as shared

    unit = _unit()
    two = {"u1": [_review("A"), _review("B")]}
    split = {
        "u1": [
            _review("A"), _review("B"),
            _review("C", decision="keep", canonical="Orpo"),
        ]
    }
    for reviews in (two, split):
        approved, _queue = reconcile.decide([unit], reviews, required=3)
        assert not approved, "the panel approved on fewer than three agreeing reviewers"

        entries = []
        for index, (name, review) in enumerate(
            (reviews["u1"][i]["reviewer"], review) for i, review in enumerate(reviews["u1"])
        ):
            entries.append(
                shared.Review(
                    batch_id="b1", label_id="u1", category="person", label="Petteri Orpo | Orpo",
                    reviewer=name, decision=review["decision"], canonical=review["canonical"],
                    wiki_title=review.get("wikipedia_title") or "",
                    wiki_url="https://en.wikipedia.org/wiki/Petteri_Orpo"
                    if review.get("wikipedia_title") else "",
                    fallback_reason="" if review.get("wikipedia_title") else "no article",
                    confidence=review["confidence"], reasoning=review["rationale"],
                    snapshot_sha256="abc123",
                )
            )
        result = shared.Ledger(entries).adjudicate(min_reviews=3)
        assert not result.approved, "the shared ledger approved on fewer than three agreeing reviewers"
