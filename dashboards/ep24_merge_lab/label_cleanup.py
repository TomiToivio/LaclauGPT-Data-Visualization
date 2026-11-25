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
    "perussuomalaisten finns party": "true finns",
    "perussuomalainen party": "true finns",
    "perussuomalainen finns party": "true finns",
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


#: Bracketed wording that describes what a thing is rather than which one it is.
_GENERIC_BRACKETS = frozenset(
    {"party", "parties", "political party", "political parties", "the party", "party members"}
)
#: Trailing words that name the kind of thing, not the thing: "fidesz party" is Fidesz.
_GENERIC_SUFFIXES = (" party",)  # "parties" is a class ("opposition parties"), not one party
#: A base that describes a position rather than naming a party. "political party" is not "political",
#: and "far-right parties" is not "far-right": the suffix rule needs a *name* in front of it.
_GENERIC_BASES = frozenset(
    {"political", "left", "right", "far-left", "far-right", "centre", "center", "left-wing",
     "right-wing", "opposition", "governing", "green", "liberal", "conservative", "socialist",
     "social democratic", "populist", "nationalist", "national", "ruling", "small", "new", "old"}
)


def fold_key(label: str) -> str:
    """The key two spellings of one label share: case, punctuation and a leading "the" ignored."""
    # Only spelling noise is folded away: case, quotes, a full stop after an abbreviation, and "&"
    # against "and". Brackets, slashes and commas are part of the label's meaning — folding them
    # turned "socialist party (psoe)" into "socialist party psoe".
    text = unicodedata.normalize("NFKC", label).casefold().replace("&", " and ")
    text = text.replace(".", " ").replace('"', "").replace("\u201c", "").replace("\u201d", "")
    text = " ".join(text.split())
    return text[4:] if text.startswith("the ") else text


def variant_merges(labels) -> dict[str, str]:
    """Decide, from one category's own vocabulary, which spellings are the same label.

    Three rules, each answerable from the vocabulary alone — no outside knowledge, no guessing:

    * spellings that differ only in case, punctuation, quotes or a leading "the" are one label, and
      the most frequent spelling represents it;
    * "``X`` party" is ``X`` **when ``X`` is itself a label of this category** — ``fidesz party`` is
      Fidesz because ``fidesz`` exists, while a lone ``green party`` is left as written;
    * a bracket that only says what the thing is (``vox (party)``) is dropped.

    Returns ``alias -> canonical`` for every spelling that should change. Nothing that would merge
    two labels the vocabulary keeps apart (plural/singular, ``right``/``rights``) is included.
    """
    counts: dict[str, int] = {}
    for label in labels:
        text = label.strip()
        if text:
            counts[text] = counts.get(text, 0) + 1

    representatives: dict[str, str] = {}
    for label in sorted(counts, key=lambda item: (-counts[item], len(item), item)):
        representatives.setdefault(fold_key(label), label)

    mapping: dict[str, str] = {}
    for label, key in ((label, fold_key(label)) for label in counts):
        canonical = representatives[key]
        if canonical != label:
            mapping[label] = canonical

    # A trailing " party" is the kind of thing, not the thing, when the bare label exists.
    bare = set(representatives.values())
    for label in list(counts):
        current = mapping.get(label, label)
        for suffix in _GENERIC_SUFFIXES:
            if current.casefold().endswith(suffix):
                stem = current[: -len(suffix)].strip()
                target = next((item for item in bare if item.casefold() == stem.casefold()), "")
                if target.casefold() in _GENERIC_BASES:
                    target = ""
                if target and target != current:
                    mapping[label] = target
                    mapping.setdefault(current, target)
                break

    # A bracket that only says what the thing is adds nothing.
    for label in list(counts):
        current = mapping.get(label, label)
        match = re.search(r"\(([^()]*)\)", current)
        if not match or _fold(match.group(1)) not in _GENERIC_BRACKETS:
            continue
        target = (current[: match.start()] + current[match.end() :]).strip(" -,")
        target = " ".join(target.split())
        if target and target != current:
            mapping[label] = target
            mapping.setdefault(current, target)

    return {alias: canonical for alias, canonical in mapping.items() if alias != canonical}


def merge_cell(cell: str, mapping: dict[str, str], separator: str = ",") -> str:
    """Apply a variant mapping to every label of one cell, collapsing labels that become equal."""
    if not cell:
        return ""
    seen: set[str] = set()
    out: list[str] = []
    for part in (item.strip() for item in cell.split(separator)):
        label = mapping.get(part, part)
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    joiner = separator + " " if separator + " " in cell else separator
    return joiner.join(out)
