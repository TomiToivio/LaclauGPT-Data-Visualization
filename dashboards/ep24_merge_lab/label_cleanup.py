"""Cleanup of raw corpus labels before they are displayed or merged (#311, owner instruction 2026-11-24).

The served dashboards carry labels exactly as the extraction wrote them: lowercase, sometimes with a
redundant annotation in brackets, sometimes with a party's native name. Two rules from the issue
apply:

* **redundant parentheticals go.** ``european union (eu)`` is one entity whose acronym adds nothing;
  ``national politics (finland)`` is not, because the bracket is what distinguishes it from another
  country's politics. Only an acronym of the label itself is dropped — never a disambiguator;
* **party names are written once, in English.** ``perussuomalaiset (ps)``, ``perussuomalaiset (finns
  party)`` and ``true finns`` are one party, and the display form is ``true finns``.

Nothing here decides identity: a label that is not obviously redundant is returned unchanged, so a
cleanup can never invent a merge.
"""
from __future__ import annotations

import re
import unicodedata

#: Party spellings that name one party. Keyed by the folded text *before* the first bracket, so
#: ``perussuomalaiset (ps)`` and ``perussuomalaiset (finns party)`` both resolve without a table row
#: per gloss.
PARTY_ALIASES: dict[str, str] = {
    "perussuomalaiset": "true finns",
    # The corpus also carries the Finnish inflections of the same party; one party, one display name.
    "perussuomalaisten": "true finns",
    "perussuomalaisia": "true finns",
    "perussuomalainen": "true finns",
    "ps": "true finns",
    "true finns": "true finns",
    "the true finns": "true finns",
    "finns party": "true finns",
    "the finns party": "true finns",
    # Spellings the served data actually carries: the extraction lost the bracket, so the gloss
    # trails the native name as separate words. One party, one display name.
    "perussuomalaiset party": "true finns",
    "perussuomalaiset ps": "true finns",
    "perussuomalaiset ps party": "true finns",
    "perussuomalaiset finns party": "true finns",
    "perussuomalaiset finland's finns party": "true finns",
    "basic finns party (perussuomalaiset)": "true finns",
    "party (perussuomalaiset)": "true finns",
    "perussuomalaiset (ps) / finns party": "true finns",
}

#: Bracketed content that is an annotation rather than part of a name.
ANNOTATIONS: frozenset[str] = frozenset(
    {"implicit", "implied", "self", "the self", "sarcastic", "ironic", "quoted", "mentioned"}
)

_TRAILING = re.compile(r"\s*\(([^()]*)\)\s*$")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def _collapse(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _initials(text: str) -> str:
    # "the european union (eu)" abbreviates as EU, not TEU: an article is not a word of the name.
    words = [word for word in re.split(r"[\s/\-]+", text) if word]
    if len(words) > 1 and words[0].casefold() in {"the", "a", "an"}:
        words = words[1:]
    return "".join(word[0] for word in words if word[0].isalpha()).casefold()


def _is_acronym(inner: str, base: str) -> bool:
    """Is ``(inner)`` an acronym of ``base``?

    ``(eu)`` of *european union*, ``(pp)`` of *partido popular*, ``(epp)`` of *european people's
    party*. Two letters minimum, six maximum, and the letters must match the initials in order —
    which is why ``(finland)`` is never dropped from *national politics*.
    """
    letters = re.sub(r"[^0-9a-z]", "", _fold(inner))
    if not 2 <= len(letters) <= 6:
        return False
    if letters.upper() == letters and len(letters) <= 5 and inner.strip().isupper():
        # "(EU)" is written as an acronym; it still has to match the words it abbreviates.
        return letters == _initials(base)
    return letters == _initials(base)


def _match_case(canonical: str, label: str) -> str:
    """Keep the display case the label already uses (served data is lowercase, source data is not)."""
    return canonical.upper() if label.strip().isupper() else (
        canonical.title() if label.strip()[:1].isupper() else canonical
    )


def clean_label(label: str) -> str:
    """The display form of one label: no redundant bracket, one party name, no leading article."""
    text = _collapse(label)
    if not text:
        return ""

    # A bracket that glosses the label itself, before anything else: "perussuomalaiset (ps)".
    match = _TRAILING.search(text)
    if match:
        base = text[: match.start()].strip()
        inner = match.group(1).strip()
        if base and (_is_acronym(inner, base) or _fold(inner) in ANNOTATIONS):
            text = base
        elif base and _fold(base) in PARTY_ALIASES:
            # The bracket is a translation or an acronym of a known party: the alias table wins.
            text = base

    # A party written by its native name is written instead by its English display name.
    folded = _fold(text)
    if folded in PARTY_ALIASES:
        return _match_case(PARTY_ALIASES[folded], label)

    if folded.startswith("the ") and len(folded) > 4:
        text = text[4:].strip()
    return text


def clean_cell(cell: str, separator: str = ",") -> str:
    """Clean every label in one list cell, preserving order and dropping repeats the cleanup created.

    ``separator`` is the character the cell uses between labels. Two labels that become equal after
    cleanup are one label; they are collapsed to the first occurrence, because showing the same
    entity twice would inflate every count that reads the cell.
    """
    if not cell:
        return ""
    parts = [part.strip() for part in cell.split(separator)]
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in parts:
        label = clean_label(part)
        if not label:
            continue
        key = _fold(label)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label)
    # Keep the spacing the cell already used between labels, so a diff of the file shows the
    # cleanup and nothing else.
    joiner = separator + " " if separator + " " in cell else separator
    return joiner.join(cleaned)
