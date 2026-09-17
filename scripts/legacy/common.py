"""Shared privacy-safe helpers for legacy specialized dashboards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "legacy-view-v1"


def stable_id(*parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def provenance(*, source_field: str, status: str, rule: str | None = None) -> dict[str, str]:
    item = {"source_field": source_field, "observation_status": status, "contract_version": CONTRACT_VERSION}
    if rule:
        item["normalization_rule"] = rule
    return item


def write_json(path: Path, payload: Any, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing destructive overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def split_tokens(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    for sep in ("|", ";", "\n"):
        text = text.replace(sep, ",")
    return [token.strip() for token in text.split(",") if token.strip()]
