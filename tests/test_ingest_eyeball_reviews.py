"""Tests for ingesting the sibling eyeball review passes (#311).

The point of these tests is that the ingest must be faithful: real provenance instead of an invented
snapshot hash, no guessed category, and no single-pass review ever masquerading as a decision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))
sys.path.insert(0, str(ROOT / "tools"))

import ingest_eyeball_reviews as ingest

INVENTORY = {"afd (alternative for germany)": {"entity"}, "borisov": {"person"}}


def _single_pass() -> dict:
    return {
        "review_scope": "Older accessible codebook labels; not current merge rows",
        "latest_run": "20261124T165037Z",
        "review_count": 1,
        "approved": False,
        "candidates": [
            {
                "category": "entity",
                "alias": "AfD (Alternative for Germany)",
                "scope": {"country": "DE"},
                "canonical_label": "Alternative for Germany",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Alternative_for_Germany",
                "status": "pending",
                "reviewer_ids": ["chatgpt-eyeball"],
                "evidence": "English Wikipedia title checked",
            }
        ],
        "flags": [
            {
                "country": "PT",
                "alias": "CDU (Democratic and Social Centre)",
                "reason": "Portuguese CDU is the Unitary Democratic Coalition",
                "sources": ["https://en.wikipedia.org/wiki/Unitary_Democratic_Coalition"],
            }
        ],
    }


def _second_pass() -> dict:
    return {
        "scope": "Accessible issue17 English label codebook only",
        "reviewer": "chatgpt-single-review",
        "approved": False,
        "proposals": [
            {
                "category": "entity",
                "alias": "Chega party",
                "scope": {"country": "PT"},
                "proposed_canonical": "Chega (political party)",
                "reference_to_verify": "https://en.wikipedia.org/wiki/Chega_(political_party)",
                "status": "proposed",
                "note": "verify before approval",
            }
        ],
        "keep_separate_checks": ["Swedish national parties vs named regional branches"],
    }


def _third_pass() -> dict:
    return {
        "scope": "All 54 registry rows inspected",
        "registry_blob_sha": "763cec1eea2fc22fa851fcceb5d26df1f647b123",
        "reviewer": "chatgpt-single-review",
        "findings": [
            {
                "labels": ["BG:Borisov", "BG:Borissov"],
                "decision": "support_same_identity",
                "sources": ["https://www.wikidata.org/wiki/Q57775"],
                "note": "QID verified",
            },
            {"labels": ["common:bolsonaro"], "decision": "challenge", "note": "surname is ambiguous"},
        ],
    }


def test_a_candidate_becomes_one_merge_review_with_real_provenance() -> None:
    parsed = ingest.parse_document(_single_pass(), "single-pass.json", INVENTORY)
    assert len(parsed.reviews) == 1
    review = parsed.reviews[0]
    assert review.decision == "merge"
    assert review.canonical == "Alternative for Germany"
    assert review.label_id == "entity:AfD (Alternative for Germany)"
    # Provenance is the scope text plus the run, not a fabricated sha256.
    assert "20261124T165037Z" in review.snapshot_sha256
    assert "Older accessible codebook" in review.snapshot_sha256


def test_a_flag_becomes_a_keep_separate_review_with_its_reason() -> None:
    inventory = {**INVENTORY, "cdu (democratic and social centre)": {"entity"}}
    parsed = ingest.parse_document(_single_pass(), "single-pass.json", inventory)
    flag = next(r for r in parsed.reviews if r.label == "CDU (Democratic and Social Centre)")
    assert flag.decision == "keep_separate"
    assert "Unitary Democratic Coalition" in flag.fallback_reason


def test_a_label_with_no_category_in_the_inventory_is_reported_not_guessed() -> None:
    parsed = ingest.parse_document(_single_pass(), "single-pass.json", INVENTORY)
    assert any(item["alias"] == "CDU (Democratic and Social Centre)" for item in parsed.unmapped)
    assert not any(r.label.startswith("CDU") for r in parsed.reviews)


def test_a_proposal_without_a_url_is_flagged_in_its_own_evidence() -> None:
    document = _second_pass()
    document["proposals"][0]["reference_to_verify"] = ""
    parsed = ingest.parse_document(document, "second.json", INVENTORY)
    review = parsed.reviews[0]
    assert "cited no URL" in review.fallback_reason


def test_free_text_keep_separate_checks_are_not_fabricated_into_labels() -> None:
    parsed = ingest.parse_document(_second_pass(), "second.json", INVENTORY)
    assert all(r.label != "Swedish national parties vs named regional branches" for r in parsed.reviews)
    assert any("free-text" in item["reason"] for item in parsed.unmapped)


def test_a_same_identity_finding_becomes_a_merge_vote_on_the_bare_label() -> None:
    parsed = ingest.parse_document(_third_pass(), "third.json", INVENTORY)
    review = next(r for r in parsed.reviews if r.label == "Borisov")
    assert review.decision == "merge"
    assert review.category == "person"
    assert "Q57775" in review.wiki_url


def test_a_challenge_finding_is_not_turned_into_a_decision() -> None:
    parsed = ingest.parse_document(_third_pass(), "third.json", INVENTORY)
    assert not any(r.label == "common:bolsonaro" for r in parsed.reviews)
    assert any("not a label-scoped merge vote" in item["reason"] for item in parsed.unmapped)


def test_every_proposed_entry_is_marked_proposed_never_approved() -> None:
    parsed = ingest.parse_document(_single_pass(), "single-pass.json", INVENTORY)
    assert parsed.proposed, "a candidate with a canonical should be visible to the Merge Lab"
    assert {entry.status for entry in parsed.proposed} == {"proposed"}
    assert all(entry.reviewers for entry in parsed.proposed)


def test_the_dry_run_writes_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "eyeball"
    directory.mkdir()
    (directory / "single-pass.json").write_text(json.dumps(_single_pass()), encoding="utf-8")
    ledger, registry = tmp_path / "ledger.jsonl", tmp_path / "registry.jsonl"
    code = ingest.main(
        [
            "--dir", str(directory),
            "--ledger", str(ledger),
            "--registry", str(registry),
            "--dry-run",
        ]
    )
    assert code == 0
    assert not ledger.exists() and not registry.exists()


def test_no_item_is_ever_dropped_silently() -> None:
    """Every item in a report must end up either as a review or in the unmapped report."""
    for document, name in (
        (_single_pass(), "single-pass.json"),
        (_second_pass(), "second.json"),
        (_third_pass(), "third.json"),
    ):
        parsed = ingest.parse_document(document, name, INVENTORY)
        items = sum(
            len(document.get(key) or ())
            for key in ("candidates", "flags", "proposals", "keep_separate_checks", "findings")
        )
        assert len(parsed.reviews) + len(parsed.unmapped) == items, name


def test_a_code_audit_finding_is_surfaced_but_never_counted_as_a_review() -> None:
    document = {
        "scope": "Peer audit of PR 314 panel machinery",
        "findings": [
            {
                "severity": "blocking",
                "file": "reconcile.py",
                "finding": "majority gets approved before adjudication",
            }
        ],
    }
    parsed = ingest.parse_document(document, "fourth.json", INVENTORY)
    assert parsed.reviews == []
    assert len(parsed.unmapped) == 1
    assert "code audit finding" in parsed.unmapped[0]["reason"]
    assert "blocking" in parsed.unmapped[0]["reason"]


def test_ingesting_the_same_file_twice_does_not_duplicate_registry_rows(tmp_path: Path) -> None:
    directory = tmp_path / "eyeball"
    directory.mkdir()
    (directory / "single-pass.json").write_text(json.dumps(_single_pass()), encoding="utf-8")
    ledger, registry = tmp_path / "ledger.jsonl", tmp_path / "registry.jsonl"
    args = ["--dir", str(directory), "--ledger", str(ledger), "--registry", str(registry)]
    ingest.main(args)
    after_first = registry.read_text(encoding="utf-8").count("\n")
    ingest.main(args)
    assert registry.read_text(encoding="utf-8").count("\n") == after_first
