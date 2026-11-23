"""Merge PLEDGE labels that mean the same thing.

The dashboard's label columns are comma-joined tag lists, and the same referent appears in several
spellings:

    european union (176)   european union eu (71)   european union, politician (112)
    politician (102)       politicians (94)         political parties, politicians (94)

So three things have to happen, in this order: split a cell into atomic labels, fold each label
through the shared alias rule, then fold plural/singular and curated synonyms, dedupe, and rejoin.
Splitting matters on its own: ``european union, politician`` is *two* tags that were counted as one
distinct string, which is why 7,722 "topics" existed for a corpus of 12,394 videos.

What is deliberately not merged: ``european union`` / ``european commission`` / ``european
parliament`` are three institutions; ``european unity`` is not ``european union``. Similar wording
is not the test — same referent is.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["MERGE_MAP", "PLURAL_FOLDS", "SEPARATORS", "merge_cell", "merge_labels", "split_cell"]

#: Separators between tags in one cell. Commas are the convention; the rest appear occasionally.
SEPARATORS = re.compile(r"\s*[,;|]\s*")

#: Synonyms and spelling variants with one referent. Keys are matched after case folding.
MERGE_MAP: dict[str, str] = {
    # The EU, written every way the tagging model found.
    "eu": "european union",
    "e.u.": "european union",
    "the eu": "european union",
    "european union eu": "european union",
    "eu european union": "european union",
    # Institutions that are *not* the union keep their own names.
    "eu commission": "european commission",
    "european commission eu": "european commission",
    "eu parliament": "european parliament",
    # Countries and blocs.
    "us": "united states",
    "usa": "united states",
    "u.s.": "united states",
    "u.s.a.": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "un": "united nations",
    "u.n.": "united nations",
}

#: Singular -> plural for tags where both spellings occur. Curated, because naive stemming
#: mangles words that merely look plural ("politics" is not "politic").
PLURAL_FOLDS: dict[str, str] = {
    "politician": "politicians",
    "voter": "voters",
    "campaigner": "campaigners",
    "journalist": "journalists",
    "activist": "activists",
    "citizen": "citizens",
    "party": "parties",
    "migrant": "migrants",
    "farmer": "farmers",
    "worker": "workers",
}


def split_cell(value: object) -> list[str]:
    """Atomic labels in one cell, order preserved, empties and nulls dropped."""
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    out: list[str] = []
    for part in SEPARATORS.split(text):
        label = re.sub(r"\s+", " ", part).strip(" .;:")
        if label and label.lower() not in {"nan", "none"}:
            out.append(label)
    return out


def merge_labels(labels: Iterable[str]) -> list[str]:
    """Fold synonyms and plurals, then dedupe while keeping first-seen order."""
    merged: list[str] = []
    for label in labels:
        key = re.sub(r"\s+", " ", str(label)).strip().casefold()
        if not key:
            continue
        canonical = MERGE_MAP.get(key) or PLURAL_FOLDS.get(key) or key
        if canonical not in merged:
            merged.append(canonical)
    return merged


def merge_cell(value: object) -> str:
    """Merge one comma-joined cell back into a cell: ``"european union eu, politician"``
    becomes ``"european union, politicians"``."""
    return ", ".join(merge_labels(split_cell(value)))
