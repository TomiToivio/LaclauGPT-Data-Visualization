"""Typed human-review state and persistence abstractions."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

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
