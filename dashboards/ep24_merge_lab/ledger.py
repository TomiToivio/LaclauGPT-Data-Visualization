"""The shared review ledger, and the adjudication that turns reviews into decisions (#311).

A ledger is not a log of opinions. It is the structure that makes the issue's central requirement
checkable: *at least three attributable reviews per label*, from *distinct* reviewers, against *the
same frozen snapshot*, with disagreements recorded rather than averaged away.

Three consequences, all enforced here:

* **Coverage is computable.** ``coverage()`` answers "which labels are short of reviewers" for any
  batch, from the file itself — so completion can be blocked on evidence rather than on a claim.
* **Adjudication is a rule, not a mood.** Unanimity across three distinct reviewers approves a merge.
  Anything else becomes a conflict and goes to a human, because a 2-to-1 vote is exactly the case
  where a wrong canonical label would overwrite two reviewers' dissent.
* **Appends are atomic.** Reviewers run in parallel; last-writer-wins would lose a review, so each
  append takes an exclusive lock and rewrites nothing.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .registry import RegistryEntry, Scope

DECISIONS = ("merge", "keep_separate")


class LedgerError(ValueError):
    """A review that cannot be trusted, or a ledger that cannot be read."""


@dataclass(frozen=True)
class Review:
    """One reviewer's judgement about one label, against one frozen snapshot."""

    batch_id: str
    label_id: str
    category: str
    label: str
    reviewer: str
    decision: str
    canonical: str = ""
    wiki_title: str = ""
    wiki_url: str = ""
    wikidata_qid: str = ""
    fallback_reason: str = ""
    polarity: str = ""
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    reasoning: str = ""
    snapshot_sha256: str = ""
    created_at: str = ""

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.batch_id.strip():
            problems.append("batch_id is empty")
        if not self.label_id.strip():
            problems.append("label_id is empty")
        if self.decision not in DECISIONS:
            problems.append(f"decision must be one of {DECISIONS}, got {self.decision!r}")
        if not self.reviewer.strip():
            problems.append("reviewer is empty — an unattributed review is not evidence")
        if self.decision == "merge":
            if not self.canonical.strip():
                problems.append("a merge needs the canonical label it merges to")
            if not (self.wiki_url.strip() or self.fallback_reason.strip()):
                problems.append("a merge must cite a verified URL or state why no article exists")
            if self.wiki_title.strip() and not self.wiki_url.strip():
                problems.append("wiki_title without the URL that was read")
        if not self.snapshot_sha256.strip():
            problems.append("no snapshot hash — the review is not tied to a frozen input")
        if not 0.0 <= float(self.confidence) <= 1.0:
            problems.append("confidence must be within 0..1")
        return problems

    def as_json(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "label_id": self.label_id,
            "category": self.category,
            "label": self.label,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "canonical": self.canonical,
            "wiki_title": self.wiki_title,
            "wiki_url": self.wiki_url,
            "wikidata_qid": self.wikidata_qid,
            "fallback_reason": self.fallback_reason,
            "polarity": self.polarity,
            "evidence": list(self.evidence),
            "confidence": float(self.confidence),
            "reasoning": self.reasoning,
            "snapshot_sha256": self.snapshot_sha256,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> Review:
        return cls(
            batch_id=str(payload.get("batch_id") or ""),
            label_id=str(payload.get("label_id") or ""),
            category=str(payload.get("category") or ""),
            label=str(payload.get("label") or ""),
            reviewer=str(payload.get("reviewer") or ""),
            decision=str(payload.get("decision") or ""),
            canonical=str(payload.get("canonical") or ""),
            wiki_title=str(payload.get("wiki_title") or ""),
            wiki_url=str(payload.get("wiki_url") or ""),
            wikidata_qid=str(payload.get("wikidata_qid") or ""),
            fallback_reason=str(payload.get("fallback_reason") or ""),
            polarity=str(payload.get("polarity") or ""),
            evidence=tuple(payload.get("evidence") or ()),
            confidence=float(payload.get("confidence") or 0.0),
            reasoning=str(payload.get("reasoning") or ""),
            snapshot_sha256=str(payload.get("snapshot_sha256") or ""),
            created_at=str(payload.get("created_at") or ""),
        )


@dataclass
class Adjudication:
    """What the ledger supports: settled decisions, conflicts, and labels short of reviewers."""

    approved: list[RegistryEntry] = field(default_factory=list)
    keep_separate: list[RegistryEntry] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    incomplete: list[dict[str, Any]] = field(default_factory=list)

    @property
    def entries(self) -> list[RegistryEntry]:
        return [*self.approved, *self.keep_separate]


class Ledger:
    """An append-only review ledger with computed coverage and adjudication."""

    def __init__(self, reviews: Iterable[Review] = (), *, path: Path | None = None) -> None:
        self.path = path
        # Latest review per (reviewer, label): a reviewer may revise their own judgement, and the
        # revision must not be counted as a second independent voice.
        self._reviews: dict[tuple[str, str], Review] = {}
        for review in reviews:
            self._reviews[(review.reviewer, review.label_id)] = review

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: Path | str) -> Ledger:
        path = Path(path)
        if not path.exists():
            raise LedgerError(f"ledger not found: {path}")
        reviews: list[Review] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                reviews.append(Review.from_json(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise LedgerError(f"{path.name}:{number}: unreadable review ({exc})") from exc
        return cls(reviews, path=path)

    def problems(self) -> list[str]:
        out: list[str] = []
        for review in self._reviews.values():
            out.extend(f"{review.label_id}/{review.reviewer}: {p}" for p in review.validate())
        return out

    # ------------------------------------------------------------------ writing

    def append(self, reviews: Iterable[Review], path: Path | str | None = None) -> Path:
        """Append reviews under an exclusive lock; never rewrite what is already there."""
        target = Path(path) if path else self.path
        if target is None:
            raise LedgerError("no ledger path to append to")
        fresh = [replace(r, created_at=r.created_at or _now()) for r in reviews]
        for review in fresh:
            problems = review.validate()
            if problems:
                raise LedgerError(f"{review.label_id}/{review.reviewer}: {'; '.join(problems)}")

        if not target.exists():
            target.write_text("", encoding="utf-8")
        handle = open(target, "a", encoding="utf-8")  # noqa: SIM115 — held across the lock
        try:
            _lock(handle)
            for review in fresh:
                handle.write(json.dumps(review.as_json(), sort_keys=True, ensure_ascii=False) + "\n")
                self._reviews[(review.reviewer, review.label_id)] = review
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            _unlock(handle)
            handle.close()
        return target

    # ------------------------------------------------------------------ coverage

    def coverage(self, batch_id: str | None = None) -> dict[str, dict[str, Any]]:
        """Per label: which reviewers covered it, how they split, and whether it is complete."""
        per_label: dict[str, dict[str, Any]] = {}
        for review in self._reviews.values():
            if batch_id and review.batch_id != batch_id:
                continue
            slot = per_label.setdefault(
                review.label_id,
                {
                    "category": review.category,
                    "label": review.label,
                    "reviewers": [],
                    "decisions": {},
                    "snapshot_hashes": set(),
                },
            )
            slot["reviewers"].append(review.reviewer)
            slot["decisions"][review.reviewer] = review.decision
            slot["snapshot_hashes"].add(review.snapshot_sha256)
        for slot in per_label.values():
            slot["reviewers"] = sorted(set(slot["reviewers"]))
            slot["review_count"] = len(slot["reviewers"])
            slot["snapshot_hashes"] = sorted(slot["snapshot_hashes"])
            slot["mixed_snapshot"] = len(slot["snapshot_hashes"]) > 1
        return per_label

    def coverage_matrix(self) -> dict[str, Any]:
        per_label = self.coverage()
        by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"labels": 0, "complete": 0})
        for slot in per_label.values():
            category = slot["category"]
            by_category[category]["labels"] += 1
            if slot["review_count"] >= 3 and not slot["mixed_snapshot"]:
                by_category[category]["complete"] += 1
        return {
            "labels_seen": len(per_label),
            "by_category": dict(sorted(by_category.items())),
            "short_of_three": sorted(
                label for label, slot in per_label.items()
                if slot["review_count"] < 3 or slot["mixed_snapshot"]
            ),
        }

    # ------------------------------------------------------------------ adjudication

    def adjudicate(self, *, min_reviews: int = 3, polarity_of: dict[str, str] | None = None) -> Adjudication:
        """Turn reviews into registry entries, or into conflicts and gaps.

        Unanimity across ``min_reviews`` distinct reviewers settles a label. Disagreement does not get
        averaged: it is recorded with every vote so a human sees who said what.
        """
        polarity_of = polarity_of or {}
        result = Adjudication()
        for label_id, slot in sorted(self.coverage().items()):
            if slot["mixed_snapshot"]:
                result.incomplete.append(
                    {
                        "label_id": label_id,
                        "reviewers": slot["reviewers"],
                        "reason": "reviews cite different snapshots",
                    }
                )
                continue
            if slot["review_count"] < min_reviews:
                result.incomplete.append(
                    {
                        "label_id": label_id,
                        "reviewers": slot["reviewers"],
                        "reason": f"{slot['review_count']} of {min_reviews} required reviews",
                    }
                )
                continue

            votes = {entry.reviewer: entry for entry in self._reviews.values() if entry.label_id == label_id}
            decisions = {vote.decision for vote in votes.values()}
            if len(decisions) > 1:
                result.conflicts.append(
                    {
                        "label_id": label_id,
                        "votes": [
                            {
                                "reviewer": vote.reviewer,
                                "decision": vote.decision,
                                "canonical": vote.canonical,
                                "evidence": list(vote.evidence),
                            }
                            for vote in sorted(votes.values(), key=lambda item: item.reviewer)
                        ],
                    }
                )
                continue

            decision = decisions.pop()
            ordered = sorted(votes.values(), key=lambda item: item.reviewer)
            sample = ordered[0]
            if decision == "keep_separate":
                canonical = ""
            else:
                canonicals = _distinct_canonicals(ordered)
                if len(canonicals) > 1:
                    # Same intent, different titles is still not a settled decision: #311 asks for the
                    # *exact* English article title, and "Hungarians" vs "Hungarian people" (a redirect)
                    # are not interchangeable as a canonical label. A human adjudicates which one.
                    result.conflicts.append(
                        {
                            "label_id": label_id,
                            "reason": "reviewers agreed to merge but named different canonicals",
                            "canonicals": canonicals,
                            "votes": [
                                {
                                    "reviewer": vote.reviewer,
                                    "decision": vote.decision,
                                    "canonical": vote.canonical,
                                    "wiki_url": vote.wiki_url,
                                    "evidence": list(vote.evidence),
                                }
                                for vote in ordered
                            ],
                        }
                    )
                    continue
                canonical = canonicals[0] if canonicals else ""
            entry = RegistryEntry(
                category=sample.category,
                alias=sample.label,
                canonical=canonical if decision == "merge" else sample.label,
                status="approved" if decision == "merge" else "keep_separate",
                canonical_id=sample.wikidata_qid,
                wiki_title=sample.wiki_title,
                wiki_url=sample.wiki_url,
                wikidata_qid=sample.wikidata_qid,
                fallback_reason=sample.fallback_reason,
                polarity=_polarity_for(sample, polarity_of.get(label_id, sample.polarity)),
                scope=Scope(),
                evidence=tuple(dict.fromkeys(item for vote in ordered for item in vote.evidence)),
                reviewers=tuple(vote.reviewer for vote in ordered),
                method="unanimous-review",
                decision=decision,
                created_at=_now(),
            )
            (result.approved if decision == "merge" else result.keep_separate).append(entry)
        return result

    def blocked_labels(self, *, min_reviews: int = 3) -> list[str]:
        """Labels that cannot yet be decided. Completion is blocked while this is non-empty."""
        return [
            label_id
            for label_id, slot in self.coverage().items()
            if slot["review_count"] < min_reviews or slot["mixed_snapshot"]
        ]


def _polarity_for(review: Review, stated: str) -> str:
    """The polarity a decision ranges over.

    A reviewer decides about a sentiment *target* ("european union"), not about whether a text was
    positive about it, so an unstated polarity means every polarity: "*". The registry then prefers a
    polarity-specific decision when one exists and falls back to the wildcard otherwise.
    """
    if review.category != "sentiment":
        return stated
    return stated or "*"


def _distinct_canonicals(votes: list[Review]) -> list[str]:
    """The canonical spellings the reviewers proposed, case-insensitively deduplicated."""
    seen: dict[str, str] = {}
    for vote in votes:
        spelling = vote.canonical.strip()
        if spelling:
            seen.setdefault(spelling.casefold(), spelling)
    return sorted(seen.values())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lock(handle: Any) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except (ImportError, OSError):  # pragma: no cover - non-POSIX
        pass


def _unlock(handle: Any) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError):  # pragma: no cover - non-POSIX
        pass
