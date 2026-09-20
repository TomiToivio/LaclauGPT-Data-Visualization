"""Typed human-review state and persistence abstractions."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

from pydantic import BaseModel, Field

ReviewStatus = Literal["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"]


class Review(BaseModel):
    source_url: str
    reviewer: str = ""
    status: ReviewStatus = "PROVISIONAL"
    dubious: bool = False
    exclude: bool = False
    wrong_language: bool = False
    note: str = ""
    corrections: dict[str, object] = Field(default_factory=dict)
    rerun_analysis: bool = False
    rerun_asr: bool = False
    rerun_ocr: bool = False
    reprocess_media: bool = False
    split_request: dict[str, object] | None = None
    cut_request: dict[str, object] | None = None
    review_version: int = 1
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def document_id(self) -> str:
        """Compatibility alias for older callers."""
        return self.source_url


class ReviewStore(Protocol):
    def save(self, review: Review) -> None: ...
    def get(self, source_url: str) -> Review | None: ...


def canonical_review_source_url(record: Mapping[str, Any]) -> str | None:
    """Return the canonical source identity when a row is eligible for Phase 1 review.

    Phase 0 compatibility rows and legacy-only rows deliberately return None.
    The function accepts either a canonical nested record or its flattened
    visualization row, where raw_record retains the canonical payload.
    """
    if record.get("phase0_compatibility"):
        return None

    raw = record.get("raw_record")
    candidate = raw if isinstance(raw, Mapping) else record
    if any(str(key).startswith("phase0") for key in candidate):
        return None

    source_url = str(candidate.get("source_url") or record.get("source_url") or "").strip()
    if not source_url:
        return None

    canonical_shape = bool(candidate.get("schema_version")) or any(
        isinstance(candidate.get(section), Mapping)
        for section in ("source", "content", "analysis")
    )
    return source_url if canonical_shape else None


def save_canonical_review(
    record: Mapping[str, Any],
    review: Review,
    store: ReviewStore,
) -> None:
    """Persist review state only for a canonical record.

    Review state is written exclusively through the review store. The supplied
    source/canonical analysis mapping is never modified.
    """
    source_url = canonical_review_source_url(record)
    if source_url is None:
        raise ValueError("Researcher Review is available only for canonical Phase 1 records")
    if review.source_url != source_url:
        raise ValueError("review source_url must match the canonical record source_url")
    store.save(review)


class SQLiteReviewStore:
    """Zero-infrastructure default review store keyed by canonical source_url."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS reviews "
                "(source_url TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def save(self, review: Review) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT INTO reviews VALUES (?, ?) "
                "ON CONFLICT(source_url) DO UPDATE SET payload=excluded.payload",
                (review.source_url, review.model_dump_json()),
            )

    def get(self, source_url: str) -> Review | None:
        with sqlite3.connect(self.path) as con:
            row = con.execute(
                "SELECT payload FROM reviews WHERE source_url=?", (source_url,)
            ).fetchone()
        return Review.model_validate_json(row[0]) if row else None


class MongoReviewStore:
    """Optional distributed review adapter. No connection occurs at import time."""

    def __init__(self, collection) -> None:
        self.collection = collection

    def save(self, review: Review) -> None:
        payload = json.loads(review.model_dump_json())
        self.collection.update_one(
            {"source_url": review.source_url}, {"$set": payload}, upsert=True
        )

    def get(self, source_url: str) -> Review | None:
        payload = self.collection.find_one({"source_url": source_url}, {"_id": 0})
        return Review.model_validate(payload) if payload else None
