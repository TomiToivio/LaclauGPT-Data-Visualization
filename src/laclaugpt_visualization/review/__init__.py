"""Human review models and local SQLite persistence."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, sqlite3
from pydantic import BaseModel, Field

class Review(BaseModel):
    document_id: str
    reviewer: str = ""
    status: str = "pending"
    dubious: bool = False
    exclude: bool = False
    note: str = ""
    corrections: dict[str, object] = Field(default_factory=dict)
    rerun_analysis: bool = False
    rerun_asr: bool = False
    rerun_ocr: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SQLiteReviewStore:
    def __init__(self, path: str | Path) -> None:
        self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con: con.execute('CREATE TABLE IF NOT EXISTS reviews (document_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    def save(self, review: Review) -> None:
        with sqlite3.connect(self.path) as con: con.execute('INSERT INTO reviews VALUES (?,?) ON CONFLICT(document_id) DO UPDATE SET payload=excluded.payload',(review.document_id,review.model_dump_json()))
    def get(self, document_id: str) -> Review | None:
        with sqlite3.connect(self.path) as con: row=con.execute('SELECT payload FROM reviews WHERE document_id=?',(document_id,)).fetchone()
        return Review.model_validate_json(row[0]) if row else None
