"""The few data shapes the merge lab passes around (#300).

Kept in one small module so the CLI, the extractor and the matcher agree on them without
importing each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: The five categories the issue names. ``person`` and ``entity`` are separate categories even
#: though both come from entity codebooks: a person is identified by a name, an organisation by
#: a legal body, and the merge rules differ.
CATEGORIES: tuple[str, ...] = ("entity", "person", "theme", "topic", "sentiment")


@dataclass(frozen=True)
class LabelStat:
    """One distinct label as the corpus actually uses it."""

    label: str
    count: int = 0
    countries: tuple[str, ...] = ()
    #: Sentiment targets only: ``positive`` / ``neutral`` / ``negative``. Polarity is part of the
    #: identity of a sentiment target — merging across it would invert meaning.
    polarity: str = ""

    @property
    def group(self) -> tuple[str, ...]:
        return (self.polarity,) if self.polarity else ()


@dataclass(frozen=True)
class Cluster:
    """A resolved group of labels, with the reasons a reader can audit."""

    canonical: str
    members: tuple[str, ...]
    confidence: float
    method: str
    count: int = 0

    def as_row(self) -> dict[str, object]:
        return {
            "canonical": self.canonical,
            "members": " | ".join(self.members),
            "member_count": len(self.members),
            "occurrences": self.count,
            "confidence": f"{self.confidence:.3f}",
            "method": self.method,
        }


@dataclass(frozen=True)
class ReviewCandidate:
    """A pair the script will not decide on its own, with the reason and the alternatives."""

    label: str
    alternatives: tuple[tuple[str, float], ...]
    reason: str

    def as_row(self) -> dict[str, object]:
        return {
            "label": self.label,
            "alternatives": " | ".join(f"{name} ({score:.3f})" for name, score in self.alternatives),
            "reason": self.reason,
        }


@dataclass
class MergeResult:
    clusters: list[Cluster] = field(default_factory=list)
    candidates: list[ReviewCandidate] = field(default_factory=list)
    #: Labels that no rule touched, kept visible so nothing silently disappears.
    singletons: list[str] = field(default_factory=list)
