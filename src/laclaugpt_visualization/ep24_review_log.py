"""Append-only review events for the EP24 workbench (#263 §4, option b).

The legacy ``:8501`` dashboard wrote a researcher's judgement into MongoDB. Option (b) of #263 keeps the
corpus read-only and makes the judgement **versioned**: every decision is one immutable line in a monthly
JSONL shard, committed to the private repository like any other research artefact.

Three rules, because a review log is a research artefact and not a UI cache:

* **Append-only.** A decision is a new event; nothing is ever rewritten or deleted. Correcting a decision
  appends another event, and the fold shows the newest value while the history stays intact.
* **Nothing is written unless the deployment says where.** ``LACLAUGPT_EP24_REVIEW_DIR`` unset means the
  workbench is read-only, and the UI says so instead of offering a form that saves nothing.
* **A public checkout is not a destination.** Review events carry researcher notes and identity. The store
  refuses a directory that sits inside the code repository it was started from.

Review events are deliberately *not* a second schema for the corpus: they contain the decision, the record
identity and the reviewer, never a copy of the transcript, the coded evidence or the analysis output.
"""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "ep24-review-event/1"

#: Environment variable that names the review directory. Unset means "read-only deployment".
REVIEW_DIR_ENV = "LACLAUGPT_EP24_REVIEW_DIR"

#: Decision fields carried over from the legacy workbench (`dashboard.py:44–100, 700–760`).
FLAGS: tuple[str, ...] = (
    "video_checked",
    "delete_video",
    "dubious_video",
    "rerun_llm",
    "rerun_ocr",
    "rerun_whisper",
)
EDITS: tuple[str, ...] = ("cut_video", "split_video")
TIMESTAMPS: tuple[str, ...] = ("cut_at", "split_at")
LISTS: tuple[str, ...] = ("new_persons", "new_themes")
TEXT: tuple[str, ...] = ("cut_keep", "researcher_note")

FIELDS: tuple[str, ...] = FLAGS + EDITS + TIMESTAMPS + LISTS + TEXT


class ReviewError(ValueError):
    """A review event that must not enter the log."""


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    recorded_at: str
    record_key: str
    country: str
    reviewer: str
    values: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "event_id": self.event_id,
            "recorded_at": self.recorded_at,
            "record_key": self.record_key,
            "country": self.country,
            "reviewer": self.reviewer,
            "values": self.values,
        }


def clean_values(values: Mapping[str, object]) -> dict[str, object]:
    """Validate a decision against the legacy vocabulary, dropping empties.

    An unknown key is refused rather than stored: a typo in a review field would otherwise enter the
    research record as a field nobody reads, and the decision it was meant to be would be lost.
    """
    cleaned: dict[str, object] = {}
    unknown = sorted(set(values) - set(FIELDS))
    if unknown:
        raise ReviewError("unknown review field(s): " + ", ".join(unknown))
    for key, value in values.items():
        if key in LISTS:
            items = [str(item).strip() for item in (value or [])] if not isinstance(value, str) else [
                part.strip() for part in value.replace(";", ",").split(",")]
            items = [item for item in items if item]
            if items:
                cleaned[key] = items
            continue
        if isinstance(value, bool):
            # An explicit False is a decision ("not dubious"), not an absent field. The UI only submits the
            # boxes a researcher ticked; a cleared flag has to mean "cleared", never "never mentioned".
            cleaned[key] = value
            continue
        text = "" if value is None else str(value).strip()
        if text:
            cleaned[key] = text
    return cleaned


@dataclass(frozen=True)
class FoldResult:
    values: dict[str, object]
    events: int
    reviewers: tuple[str, ...]


class ReviewStore:
    """A directory of monthly JSONL shards, read back into per-record state."""

    def __init__(self, directory: str | Path | None, *, application_root: str | Path | None = None):
        self.directory = Path(directory).expanduser() if directory else None
        self.application_root = Path(application_root).resolve() if application_root else None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None,
                         *, application_root: str | Path | None = None) -> ReviewStore:
        env = environment if environment is not None else os.environ
        return cls(env.get(REVIEW_DIR_ENV) or None, application_root=application_root)

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    def unsafe_reason(self) -> str:
        """Why this destination must not be written to, or an empty string when it is acceptable."""
        if self.directory is None:
            return "no review directory configured"
        target = self.directory.resolve()
        if self.application_root is not None and self.application_root in target.parents:
            return ("the configured review directory is inside the code checkout; review events must not "
                    "be written into a repository that is published")
        return ""

    def _shard(self, when: datetime) -> Path:
        assert self.directory is not None
        return self.directory / f"events-{when:%Y-%m}.jsonl"

    def append(self, record_key: str, country: str, values: Mapping[str, object], *,
               reviewer: str = "", when: datetime | None = None) -> ReviewEvent:
        """Append one decision. Returns the stored event; raises rather than pretending to save."""
        if not self.enabled:
            raise ReviewError("review writing is not configured (" + REVIEW_DIR_ENV + " is unset)")
        reason = self.unsafe_reason()
        if reason:
            raise ReviewError(reason)
        key = str(record_key or "").strip()
        if not key:
            raise ReviewError("a review event needs the record it belongs to")
        cleaned = clean_values(values)
        if not cleaned:
            raise ReviewError("a review event needs at least one decision")

        stamp = when or datetime.now(UTC)
        event = ReviewEvent(
            event_id=uuid.uuid4().hex,
            recorded_at=stamp.astimezone(UTC).isoformat(timespec="seconds"),
            record_key=key,
            country=str(country or "").strip(),
            reviewer=str(reviewer or "").strip(),
            values=cleaned,
        )
        path = self._shard(stamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        # append-only, one line per decision: a reader never sees a half-written event from another writer.
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def shards(self) -> list[Path]:
        if not self.enabled or not self.directory.is_dir():
            return []
        return sorted(self.directory.glob("events-*.jsonl"))

    def read(self) -> tuple[list[ReviewEvent], list[str]]:
        """Every readable event plus one warning per unusable line.

        A corrupt line is skipped and reported: a review log that throws on one bad byte loses every
        decision after it, and the researcher cannot tell that the log is intact but unreadable.
        """
        events: list[ReviewEvent] = []
        warnings: list[str] = []
        for shard in self.shards():
            with shard.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        warnings.append(f"{shard.name}:{number} is not valid JSON")
                        continue
                    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
                        warnings.append(f"{shard.name}:{number} is not a {SCHEMA} event")
                        continue
                    events.append(ReviewEvent(
                        event_id=str(payload.get("event_id") or ""),
                        recorded_at=str(payload.get("recorded_at") or ""),
                        record_key=str(payload.get("record_key") or ""),
                        country=str(payload.get("country") or ""),
                        reviewer=str(payload.get("reviewer") or ""),
                        values=dict(payload.get("values") or {}),
                    ))
        return events, warnings

    def fold(self, record_key: str) -> FoldResult:
        """The current decision for one record: newest value per field, history kept in the log."""
        events, _ = self.read()
        selected = [event for event in events if event.record_key == str(record_key)]
        values: dict[str, object] = {}
        reviewers: list[str] = []
        for event in selected:
            if event.reviewer and event.reviewer not in reviewers:
                reviewers.append(event.reviewer)
            for key, value in event.values.items():
                if key in LISTS:
                    existing = list(values.get(key) or [])
                    values[key] = existing + [item for item in value if item not in existing]
                else:
                    values[key] = value
        return FoldResult(values=values, events=len(selected), reviewers=tuple(reviewers))

    def summary(self) -> dict[str, object]:
        events, warnings = self.read()
        return {
            "events": len(events),
            "records": len({event.record_key for event in events}),
            "reviewers": sorted({event.reviewer for event in events if event.reviewer}),
            "warnings": warnings,
            "directory": str(self.directory) if self.directory else "",
            "enabled": self.enabled,
        }


def decisions_from_form(values: Iterable[tuple[str, object]]) -> dict[str, object]:
    """Form rows into a decision mapping, ignoring fields the researcher left empty."""
    return {key: value for key, value in values if value not in (None, "", False, [], ())}


def shard_names(events: Sequence[ReviewEvent]) -> list[str]:
    """Distinct months in a set of events, oldest first — what a commit message wants to name."""
    return sorted({event.recorded_at[:7] for event in events if event.recorded_at})
