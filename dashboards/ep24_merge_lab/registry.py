"""The shared merge registry: one durable record per scoped alias decision (#311).

The registry is not an output of a merge run — it is the *input* the runs, the dashboards and the
human Merge Lab all share. Every line says: in this category, this alias, under these constraints,
is that canonical label, and here is who decided it and on what evidence.

Design rules, from the issue:

* append-only. A decision is never rewritten in place; a correction is a new revision of the same
  record, so history survives and a rollback is a matter of pinning an earlier revision.
* attributable. Reviewer IDs, evidence and timestamps are mandatory, so no anonymous bulk import can
  masquerade as a review.
* scoped. A mapping may be restricted to a country, a language or a source, because "the party" means
  different parties in different countries.
* pinned. A run records the registry version and checksum it consumed, so a result can be reproduced
  after the registry has moved on.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CATEGORIES = ("entity", "person", "theme", "topic", "sentiment")
STATUSES = ("approved", "proposed", "rejected", "keep_separate", "superseded")
#: Who may settle a mapping. An AI panel needs three independent reviewers in unanimity; a human
#: needs one attributable, snapshot-scoped, attested decision (owner instruction, 2026-11-24).
APPROVALS = ("", "ai-panel", "human")


class RegistryError(ValueError):
    """A registry file that cannot be trusted."""


@dataclass(frozen=True)
class HumanReview:
    """Proof that a person, not a model, settled this mapping.

    A reviewer *name* in a JSON file proves nothing — an agent can type one. What makes a human
    decision checkable is that it cites the trusted review session that recorded it: the session id
    is issued by the authenticated review workflow, and the registry only applies the mapping while
    that session exists in the trusted ledger.
    """

    reviewer: str = ""
    at: str = ""
    #: Digest of the frozen input snapshot the person was looking at.
    snapshot: str = ""
    #: Session id issued by the trusted review workflow (Merge Lab / review UI).
    session: str = ""
    note: str = ""

    def as_json(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_json(cls, payload: dict[str, Any] | None) -> HumanReview:
        payload = payload or {}
        return cls(
            reviewer=str(payload.get("reviewer") or ""),
            at=str(payload.get("at") or ""),
            snapshot=str(payload.get("snapshot") or ""),
            session=str(payload.get("session") or ""),
            note=str(payload.get("note") or ""),
        )


@dataclass(frozen=True)
class Scope:
    """Where a mapping is allowed to apply. Empty means "everywhere in this category"."""

    country: str = ""
    language: str = ""
    source: str = ""

    def matches(self, country: str = "", language: str = "", source: str = "") -> bool:
        if self.country and self.country.casefold() != (country or "").casefold():
            return False
        if self.language and self.language.casefold() != (language or "").casefold():
            return False
        return not (self.source and self.source.casefold() != (source or "").casefold())

    def key(self) -> tuple[str, str, str]:
        return (self.country.casefold(), self.language.casefold(), self.source.casefold())


@dataclass(frozen=True)
class RegistryEntry:
    """One alias decision."""

    category: str
    alias: str
    canonical: str
    status: str = "approved"
    #: Stable identifier for the canonical referent, when one exists (Wikidata QID, internal ID, ...).
    canonical_id: str = ""
    wiki_title: str = ""
    wiki_url: str = ""
    wikidata_qid: str = ""
    #: Why no exact English Wikipedia title applies, when that is the case.
    fallback_reason: str = ""
    polarity: str = ""
    scope: Scope = field(default_factory=Scope)
    evidence: tuple[str, ...] = ()
    reviewers: tuple[str, ...] = ()
    method: str = ""
    decision: str = ""
    created_at: str = ""
    revision: int = 1
    supersedes: str = ""
    #: ``ai-panel`` (three-reviewer unanimity) or ``human`` (one attested person). Empty means
    #: ``ai-panel`` — the rule that existed before human approval was introduced.
    approval: str = ""
    human_review: HumanReview = field(default_factory=HumanReview)

    def validate(self) -> list[str]:
        """Everything that makes a record unusable, named. Empty means the record is sound."""
        problems: list[str] = []
        if self.category not in CATEGORIES:
            problems.append(f"unknown category {self.category!r}")
        if not self.alias.strip():
            problems.append("alias is empty")
        if self.status not in STATUSES:
            problems.append(f"unknown status {self.status!r}")
        if self.approval not in APPROVALS:
            problems.append(f"unknown approval {self.approval!r}; expected one of {APPROVALS}")
        if self.status in {"approved", "keep_separate"} and not self.canonical.strip():
            problems.append("approved/keep_separate needs a canonical label")
        if self.status == "keep_separate" and self.alias.strip() != self.canonical.strip():
            problems.append("keep_separate must point at itself")
        if not self.reviewers:
            problems.append("no reviewer recorded — a decision must be attributable")
        if self.status == "approved" and not self.evidence:
            problems.append("approved mapping carries no evidence")
        if self.category == "sentiment" and self.status in {"approved", "keep_separate"} and not self.polarity:
            problems.append("sentiment mapping must state its polarity")
        if self.wiki_title and not self.wiki_url:
            problems.append("wiki_title needs the verified URL that was actually read")
        if self.approval == "human":
            problems.extend(self._human_problems())
        elif self.status == "approved" and len(set(self.reviewers)) < 3:
            problems.append("approved mapping requires three distinct reviewer IDs")
        return problems

    def _human_problems(self) -> list[str]:
        """What an attested human decision must carry before it may settle a mapping."""
        problems: list[str] = []
        if self.status not in {"approved", "keep_separate"}:
            problems.append("a human approval must be an approved or keep_separate decision")
        review = self.human_review
        if not review.reviewer.strip():
            problems.append("human approval must name the reviewer who gave it")
        if not review.at.strip():
            problems.append("human approval must record when it was given")
        if not review.snapshot.strip():
            problems.append("human approval must name the frozen snapshot it was given against")
        if not review.session.strip():
            problems.append("human approval must cite the trusted review session that recorded it")
        if review.reviewer.strip() and review.reviewer.strip() not in {
            reviewer.strip() for reviewer in self.reviewers
        }:
            problems.append("the human reviewer must appear among the recorded reviewers")
        return problems

    def identity(self) -> str:
        """What this decision is about: category + alias + scope. Revision is not part of it."""
        return "|".join((self.category, self.alias.strip().casefold(), self.polarity.casefold(), *self.scope.key()))

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scope"] = asdict(self.scope)
        payload["human_review"] = asdict(self.human_review)
        payload["evidence"] = list(self.evidence)
        payload["reviewers"] = list(self.reviewers)
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> RegistryEntry:
        scope = Scope(**(payload.get("scope") or {}))
        return cls(
            category=str(payload["category"]),
            alias=str(payload["alias"]),
            canonical=str(payload.get("canonical") or ""),
            status=str(payload.get("status") or "approved"),
            canonical_id=str(payload.get("canonical_id") or ""),
            wiki_title=str(payload.get("wiki_title") or ""),
            wiki_url=str(payload.get("wiki_url") or ""),
            wikidata_qid=str(payload.get("wikidata_qid") or ""),
            fallback_reason=str(payload.get("fallback_reason") or ""),
            polarity=str(payload.get("polarity") or ""),
            scope=scope,
            evidence=tuple(payload.get("evidence") or ()),
            reviewers=tuple(payload.get("reviewers") or ()),
            method=str(payload.get("method") or ""),
            decision=str(payload.get("decision") or ""),
            created_at=str(payload.get("created_at") or ""),
            revision=int(payload.get("revision") or 1),
            supersedes=str(payload.get("supersedes") or ""),
            approval=str(payload.get("approval") or ""),
            human_review=HumanReview.from_json(payload.get("human_review")),
        )


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Registry:
    """A loaded registry: entries in file order, plus the lookups the pipelines need."""

    def __init__(self, entries: Iterable[RegistryEntry] = (), *, source: Path | None = None) -> None:
        self.entries: list[RegistryEntry] = list(entries)
        self.source = source
        self._latest: dict[str, RegistryEntry] = {}
        for entry in self.entries:
            if entry.status == "superseded":
                continue
            current = self._latest.get(entry.identity())
            if current is None or entry.revision >= current.revision:
                self._latest[entry.identity()] = entry

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: Path | str, *, validate: bool = True) -> Registry:
        path = Path(path)
        if not path.exists():
            raise RegistryError(f"registry not found: {path}")
        entries: list[RegistryEntry] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RegistryError(f"{path.name}:{number}: not JSON ({exc})") from exc
            try:
                entries.append(RegistryEntry.from_json(payload))
            except (KeyError, TypeError) as exc:
                raise RegistryError(f"{path.name}:{number}: record is not a decision ({exc})") from exc
        registry = cls(entries, source=path)
        if validate:
            problems = registry.problems()
            if problems:
                raise RegistryError("; ".join(problems[:5]))
        return registry

    def problems(self) -> list[str]:
        out: list[str] = []
        for entry in self.entries:
            for problem in entry.validate():
                out.append(f"{entry.category}/{entry.alias}: {problem}")
        return out

    # ------------------------------------------------------------------ identity

    @property
    def version(self) -> str:
        """Content hash of the file, so a run can name exactly what it consumed."""
        payload = json.dumps([entry.as_json() for entry in self.entries], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def latest(self, category: str, alias: str, *, country: str = "", language: str = "", source: str = "", polarity: str = "") -> RegistryEntry | None:
        """The in-force decision for this alias in this context, most specific scope first."""
        candidates = [
            entry
            for entry in self._latest.values()
            if entry.category == category
            and entry.alias.strip().casefold() == alias.strip().casefold()
            and entry.scope.matches(country, language, source)
            and (
                category != "sentiment"
                or (bool(polarity) and entry.polarity.casefold() in {polarity.casefold(), "*"})
            )
        ]
        if not candidates:
            return None
        # A polarity-specific decision beats a wildcard one; "*" only applies when nothing narrower
        # governs the polarity the caller is actually asking about.
        if category == "sentiment":
            exact = [entry for entry in candidates if entry.polarity.casefold() != "*"]
            if exact:
                candidates = exact
        specificity = max(sum(bool(part) for part in entry.scope.key()) for entry in candidates)
        best = [entry for entry in candidates if sum(bool(part) for part in entry.scope.key()) == specificity]
        if len({(entry.status, entry.canonical, entry.canonical_id) for entry in best}) != 1:
            return None
        return best[0]

    def has_alias(self, category: str, alias: str) -> bool:
        """Whether any decision exists for this alias, whatever its scope.

        A scoped decision still means the alias is spoken for: looking it up without a country must not
        report it as absent and append a duplicate.
        """
        folded = alias.strip().casefold()
        return any(
            entry.category == category and entry.alias.strip().casefold() == folded
            for entry in self._latest.values()
        )

    def duplicates(self) -> dict[tuple[str, str], int]:
        """In-force decisions that collide on (category, alias) across scopes."""
        counts: dict[tuple[str, str], int] = {}
        for entry in self._latest.values():
            key = (entry.category, entry.alias.strip().casefold())
            counts[key] = counts.get(key, 0) + 1
        return {key: count for key, count in counts.items() if count > 1}

    def unattested_human_approvals(self, trusted: dict[str, str]) -> list[str]:
        """Human approvals whose review session is not in the trusted ledger.

        ``trusted`` maps a session id issued by the authenticated review workflow to the person it
        authenticated. An approval that cites an unknown session is not evidence of a human
        decision, so it is reported here rather than silently trusted.
        """
        missing: list[str] = []
        for entry in self._latest.values():
            if entry.approval != "human":
                continue
            session = entry.human_review.session.strip()
            if not session or session not in trusted:
                missing.append(f"{entry.category}/{entry.alias}: session {session!r} is not attested")
            elif trusted[session].strip().casefold() != entry.human_review.reviewer.strip().casefold():
                missing.append(
                    f"{entry.category}/{entry.alias}: session {session!r} was authenticated as "
                    f"{trusted[session]!r}, not {entry.human_review.reviewer!r}"
                )
        return sorted(missing)

    def map_label(
        self,
        category: str,
        alias: str,
        *,
        country: str = "",
        language: str = "",
        source: str = "",
        polarity: str = "",
        trusted: dict[str, str] | None = None,
    ) -> str:
        """The canonical label for this alias, or the alias unchanged when nothing applies.

        ``keep_separate`` returns the alias itself, which is the point: an explicit non-merge must
        survive into every later run without being re-litigated.

        A human approval also has to be attested: pass ``trusted`` (session id -> authenticated
        person) and an entry whose session is absent from it is treated as unsettled. Without that
        argument human approvals do not apply either, so a forgotten ledger fails closed instead of
        letting a typed-in reviewer name rewrite the corpus.
        """
        entry = self.latest(
            category, alias, country=country, language=language, source=source, polarity=polarity
        )
        # Only settled decisions rewrite output. A proposal is evidence for the review queue, not a
        # canonicalisation: applying unapproved mappings is how one reviewer silently reseals the whole
        # corpus.
        if entry is None or entry.status not in {"approved", "keep_separate"}:
            return alias
        if entry.approval == "human":
            session = entry.human_review.session.strip()
            if not trusted or not session or session not in trusted:
                return alias
            if trusted[session].strip().casefold() != entry.human_review.reviewer.strip().casefold():
                return alias
        return entry.canonical or alias

    # ------------------------------------------------------------------ writing

    def append(self, entries: Iterable[RegistryEntry], path: Path | str | None = None) -> Path:
        """Append decisions atomically; the target is the file this registry was loaded from."""
        target = Path(path) if path else self.source
        if target is None:
            raise RegistryError("no registry path to append to")
        fresh = list(entries)
        for entry in fresh:
            problems = entry.validate()
            if problems:
                raise RegistryError(f"{entry.category}/{entry.alias}: {'; '.join(problems)}")
        with target.open("a", encoding="utf-8") as handle:
            for entry in fresh:
                if not entry.created_at:
                    entry = replace(entry, created_at=now())
                handle.write(json.dumps(entry.as_json(), sort_keys=True, ensure_ascii=False) + "\n")
        return target

    # ------------------------------------------------------------------ exports

    def iter_entries(self) -> Iterator[RegistryEntry]:
        return iter(self.entries)

    def to_csv(self, path: Path | str) -> Path:
        """Deterministic CSV: same registry in, byte-identical file out."""
        import csv

        target = Path(path)
        columns = [
            "category", "alias", "canonical", "status", "canonical_id", "polarity",
            "country", "language", "source", "wiki_title", "wiki_url", "wikidata_qid",
            "fallback_reason", "reviewers", "evidence", "method", "revision", "created_at",
        ]
        rows = []
        for entry in sorted(self.entries, key=lambda item: (item.category, item.alias.casefold(), item.identity())):
            rows.append(
                {
                    "category": entry.category,
                    "alias": entry.alias,
                    "canonical": entry.canonical,
                    "status": entry.status,
                    "canonical_id": entry.canonical_id,
                    "polarity": entry.polarity,
                    "country": entry.scope.country,
                    "language": entry.scope.language,
                    "source": entry.scope.source,
                    "wiki_title": entry.wiki_title,
                    "wiki_url": entry.wiki_url,
                    "wikidata_qid": entry.wikidata_qid,
                    "fallback_reason": entry.fallback_reason,
                    "reviewers": ";".join(entry.reviewers),
                    "evidence": " | ".join(entry.evidence),
                    "method": entry.method,
                    "revision": entry.revision,
                    "created_at": entry.created_at,
                }
            )
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return target
