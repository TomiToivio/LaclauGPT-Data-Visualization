"""Turn three independent reviews into one defensible decision (#311).

The rules follow the issue and nothing else:

* **unanimous** — all reviewers agree on decision *and* canonical name: approved automatically;
* **two of three** — a proposal only; the human queue retains all votes and any adjudicator evidence;
* **anything else** — goes to the human queue. It is not averaged, and it is never guessed.

Two further guards: a reviewer that failed is not a vote, and a prior human decision is not
overwritten — a conflict is reported.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import ledger


def _canonical_key(review: dict[str, Any]) -> str:
    return (review.get("wikipedia_title") or review["canonical"]).casefold().strip()


def unanimous(reviews: list[dict[str, Any]]) -> bool:
    if len({review["reviewer"] for review in reviews}) < 3:
        return False
    return len({review["decision"] for review in reviews}) == 1 and len(
        {_canonical_key(review) for review in reviews}
    ) == 1


def majority(reviews: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The decision a strict majority of distinct reviewers reached, or None."""
    votes = Counter(review["decision"] for review in reviews)
    decision, count = votes.most_common(1)[0]
    if count * 2 <= len(reviews):
        return None
    winners = [review for review in reviews if review["decision"] == decision]
    # Among the majority, prefer the name the most of them chose; ties keep the first by name.
    names = Counter(_canonical_key(review) for review in winners)
    best = names.most_common(1)[0][0]
    chosen = next(review for review in winners if _canonical_key(review) == best)
    return chosen


def decide(
    units: list[dict[str, Any]],
    reviews: dict[str, list[dict[str, Any]]],
    *,
    required: int = 3,
    prior: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(approved, human_queue)`` with the evidence that produced each."""
    required = max(3, required)
    prior = prior or {}
    approved: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    for unit in units:
        found = reviews.get(unit["unit_id"], [])
        distinct = {
            review["reviewer"]: review for review in found
            if review.get("reviewer") and review.get("type", "review") == "review"
            and review.get("decision") in {"merge", "keep", "split"}
            and review.get("canonical")
        }
        if len(distinct) < required:
            queue.append(
                {
                    "unit_id": unit["unit_id"],
                    "category": unit["category"],
                    "reason": f"only {len(distinct)} of {required} independent reviews",
                    "unit": unit,
                }
            )
            continue
        panel = list(distinct.values())
        base = {
            "unit_id": unit["unit_id"],
            "category": unit["category"],
            "kind": unit["kind"],
            "labels": unit["labels"],
            "countries": unit.get("countries", []),
            "occurrences": unit.get("occurrences", 0),
            "reviews": [
                {key: review.get(key) for key in ("reviewer", "model", "decision", "canonical",
                                                  "wikipedia_title", "confidence", "rationale")}
                for review in panel
            ],
        }
        previous = prior.get(unit["unit_id"]) or prior.get(
            json.dumps([unit["category"], sorted(unit["labels"])], ensure_ascii=False)
        )
        decision = None
        if unanimous(panel) and panel[0]["decision"] == "merge":
            decision = {
                **base,
                "status": "approved",
                "method": "unanimous",
                "decision": panel[0]["decision"],
                "canonical": panel[0]["canonical"],
                "wikipedia_title": panel[0].get("wikipedia_title"),
                "confidence": min(review["confidence"] for review in panel),
                "rationale": panel[0].get("rationale", ""),
            }
        if decision is None:
            queue.append(
                {
                    "unit_id": unit["unit_id"],
                    "category": unit["category"],
                    "reason": "no consensus for a merge; human review or explicit non-merge required",
                    "status": "proposed",
                    "unit": unit,
                    "reviews": base["reviews"],
                }
            )
            continue
        if previous and (
            previous.get("decision") != decision["decision"]
            or (previous.get("canonical") or "").casefold() != (decision["canonical"] or "").casefold()
        ):
            # A human already decided; the panel does not get to overrule it silently.
            queue.append({**decision, "status": "conflict", "reason": "prior human decision",
                          "conflict_with_human": previous, "unit": unit})
            continue
        approved.append(decision)
    return approved, queue


def apply_adjudications(
    approved: list[dict[str, Any]], adjudications: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compatibility helper: adjudications cannot silently rewrite settled decisions."""
    return approved


def attach_adjudications(
    queue: list[dict[str, Any]], adjudications: dict[str, dict[str, Any]]
) -> None:
    """Retain adjudicator evidence for human adjudication without granting approval."""
    for item in queue:
        verdict = adjudications.get(item["unit_id"])
        if verdict:
            item["adjudication_proposal"] = verdict


def load_prior(path: Path) -> dict[str, dict[str, Any]]:
    """Human decisions from the review UI, keyed the way a unit is keyed.

    The UI decides about labels rather than units, so the mapping is by sorted member list: a
    prior merge of exactly these labels is the same decision.
    """
    if not path.exists():
        return {}
    prior: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        members = sorted(record.get("members", []))
        if not members:
            continue
        key = json.dumps([record.get("category"), members], ensure_ascii=False)
        prior[key] = record
    return prior


def write_reports(
    out_dir: Path,
    approved: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "approved.jsonl").open("w", encoding="utf-8") as handle:
        for item in approved:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    with (out_dir / "human_queue.jsonl").open("w", encoding="utf-8") as handle:
        for item in queue:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def summary(path: Path) -> dict[str, Any]:
    """Counts from an approved.jsonl, for the release manifest and the report."""
    counts: Counter[str] = Counter()
    if not path.exists():
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        counts[f"{item['category']}:{item['method']}"] += 1
        counts[f"{item['category']}:{item['decision']}"] += 1
    return dict(sorted(counts.items()))


__all__ = [
    "apply_adjudications",
    "decide",
    "ledger",
    "load_prior",
    "majority",
    "summary",
    "unanimous",
    "write_reports",
]
