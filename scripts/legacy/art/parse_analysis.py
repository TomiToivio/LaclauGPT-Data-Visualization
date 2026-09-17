"""Parse legacy art analysis Markdown into auditable concept rows."""
from __future__ import annotations

import re
from collections.abc import Iterable

from scripts.legacy.common import provenance

SECTION_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")

DEFAULT_NOISE = {"analysis", "summary", "response", "themes", "entities", "sentiment"}


def canonicalize(term: str, aliases: dict[str, str] | None = None) -> str:
    cleaned = re.sub(r"[`*_>#]", "", term).strip(" .:-\t").casefold()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (aliases or {}).get(cleaned, cleaned)


def parse_analysis(text: str, *, source_id: str, aliases: dict[str, str] | None = None, noise: Iterable[str] = DEFAULT_NOISE) -> list[dict]:
    section = "unsectioned"
    noise_set = {canonicalize(item) for item in noise}
    rows: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        heading = SECTION_RE.match(line)
        if heading:
            section = canonicalize(heading.group(1)) or "unsectioned"
            continue
        bullet = BULLET_RE.match(line)
        if not bullet:
            continue
        raw = bullet.group(1).strip()
        canonical = canonicalize(raw, aliases)
        if not canonical or canonical in noise_set:
            continue
        rows.append({
            "source_id": source_id,
            "section": section,
            "concept_family": section,
            "raw_term": raw,
            "canonical_term": canonical,
            "weight": 1,
            "provenance": provenance(source_field="summary_analysis", status="parsed", rule="markdown_sections_v1"),
            "line_number": line_number,
        })
    return rows
