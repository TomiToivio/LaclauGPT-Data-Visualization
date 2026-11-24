"""Label normalization for the legacy EP24 merge lab (#300).

Normalization answers one question: *would a researcher reading both labels say they are the
same string?* It deliberately does not decide identity — that belongs to `similarity.py`, which
knows that ``Orpo`` and ``Petteri Orpo`` are a person question and ``Social Europe`` and
``Arguments for Europe`` are not a theme question at all.

Everything here is pure and deterministic so a run can be reproduced byte for byte.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Honorifics and office words that carry no identity. Stripped from the **front** only: a
#: trailing "minister" is usually part of the name a researcher chose ("Prime Minister Orpo").
HONORIFICS: tuple[str, ...] = (
    "prime minister",
    "deputy prime minister",
    "foreign minister",
    "finance minister",
    "minister",
    "president",
    "chancellor",
    "premier",
    "pm",
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "professor",
    "sir",
    "madam",
    "pres",
)

#: Corporate suffixes. Two labels differing only by these are the same organisation.
LEGAL_SUFFIXES: tuple[str, ...] = (
    "oy",
    "oyj",
    "ab",
    "abp",
    "as",
    "asa",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "srl",
    "spa",
    "bv",
    "nv",
    "inc",
    "ltd",
    "llc",
    "plc",
    "corp",
    "co",
)

#: Quotation and dash variants that different extractors emit for the same title.
_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
    }
)

_PUNCTUATION = re.compile(r"[^\w\s'-]", flags=re.UNICODE)
_SPACE = re.compile(r"\s+")
_APOSTROPHE_TAIL = re.compile(r"(?:'s|’s)$", flags=re.UNICODE)


@dataclass(frozen=True)
class Normalized:
    """One label, folded for comparison, with the pieces the matcher needs."""

    raw: str
    folded: str
    tokens: tuple[str, ...]
    #: Token string with honorifics and legal suffixes removed — what identity is matched on.
    core_tokens: tuple[str, ...]

    @property
    def core(self) -> str:
        return " ".join(self.core_tokens)

    @property
    def key(self) -> str:
        """Token-set key: word order does not make two labels different (``Orpo Petteri``)."""
        return " ".join(sorted(set(self.core_tokens)))


def strip_annotations(text: str) -> str:
    """Remove a parenthetical gloss: *European Broadcasting Union (EBU)* -> *European Broadcasting Union*.

    Only entity and person labels are normalised this way. A theme such as
    *European Parliament elections (2024)* carries the year as meaning, and dropping it there
    would merge two different elections.
    """
    value = unicodedata.normalize("NFC", text).strip()
    while re.search(r"\([^()]*\)", value):
        value = re.sub(r"\([^()]*\)", " ", value)
    value = re.sub(r"\([^)]*$", "", value)
    value = _SPACE.sub(" ", value.replace(")", " ")).strip(" ,;:-")
    return value.strip() or text.strip()


def strip_leading_article(text: str) -> str:
    """Drop a leading definite article: *the European Union* -> *European Union*.

    This one is safe for every category — an article never carries identity — unlike the
    parenthetical stripping above.
    """
    return re.sub(r"^the\s+", "", text, flags=re.IGNORECASE).strip()


def clean_label(text: str) -> str:
    """Both of the above, for display names of entity and person labels."""
    return strip_leading_article(strip_annotations(text)) or text.strip()


def fold(text: str) -> str:
    """Unicode-normalize, case-fold, and collapse the whitespace/punctuation extractors add."""
    normalized = unicodedata.normalize("NFKC", strip_leading_article(text)).translate(_TRANSLATION).casefold()
    normalized = _PUNCTUATION.sub(" ", normalized)
    normalized = normalized.replace("_", " ")
    normalized = _APOSTROPHE_TAIL.sub("", normalized.strip())
    normalized = _SPACE.sub(" ", normalized).strip()
    return normalized.strip("-'").strip()


def _strip_leading(tokens: list[str], vocabulary: tuple[str, ...]) -> list[str]:
    """Remove leading vocabulary entries, longest phrase first, until nothing matches."""
    changed = True
    while changed and tokens:
        changed = False
        for phrase in sorted(vocabulary, key=lambda item: -len(item.split())):
            words = phrase.split()
            if tokens[: len(words)] == words:
                tokens = tokens[len(words) :]
                changed = True
                break
    return tokens


def normalize_label(
    raw: str,
    *,
    strip_titles: bool = False,
    strip_legal_suffixes: bool = False,
    strip_parentheticals: bool = False,
) -> Normalized:
    """Fold one label and, where the category allows it, drop words that carry no identity.

    ``strip_titles`` is for people (``PM Orpo`` -> ``orpo``) and ``strip_legal_suffixes`` for
    organisations (``Fortum Oyj`` -> ``fortum``). Neither is applied to themes, topics or
    sentiment targets, where every word can carry meaning.
    """
    folded = fold(strip_annotations(raw) if strip_parentheticals else raw)
    tokens = folded.split() if folded else []
    core = list(tokens)
    if strip_titles:
        core = _strip_leading(core, HONORIFICS)
    if strip_legal_suffixes:
        core = [token for token in core if token not in LEGAL_SUFFIXES]
    return Normalized(
        raw=raw.strip(),
        folded=folded,
        tokens=tuple(tokens),
        core_tokens=tuple(core) or tuple(tokens),
    )


_PARENTHETICAL = re.compile(r"^(?P<base>.+?)\s*\((?P<qualifier>[^()]{1,40})\)\s*$")

#: Qualifiers that only repeat what the base already says ("green movement (movement)").
REDUNDANT_QUALIFIERS: frozenset[str] = frozenset(
    {"party", "political party", "the party", "movement", "coalition", "alliance", "group"}
)

#: Words that make a parenthetical informative rather than redundant: it names a *different* thing.
_KEEP_IN_BASE = frozenset({"party", "movement", "coalition", "alliance", "group"})

#: A short name may carry its organisation type in brackets: "vox (party)" is still Vox.
_ORGANISATION_TYPES = frozenset(
    {"party", "political party", "movement", "coalition", "alliance", "group", "front"}
)

#: ...but not when the short name *is* the generic word, where the bracket may be the only content.
_GENERIC_BASES = frozenset(
    {
        "government",
        "party",
        "coalition",
        "group",
        "alliance",
        "movement",
        "parliament",
        "commission",
        "council",
        "speaker",
        "minister",
        "president",
        "court",
        "union",
    }
)


def redundant_qualifier(label: str) -> str | None:
    """The base label when a trailing parenthetical adds nothing, else ``None``.

    "social democratic party (sdp)" is one party written two ways: the qualifier is the acronym of
    the words in front of it, so the base is the referent. That is the whole rule, and it is
    deliberately narrow:

    * an acronym of the base's initials, in any letter order ("sdp"/"spd"), or
    * a qualifier the base already carries ("green movement (movement)").

    Anything else is left alone, because "government (france)" and "government (spain)" are two
    governments, "speaker (jorge buxadé)" names a person, and a year or a place is information, not
    noise. Stripping those would merge different referents — the one failure mode that silently
    corrupts every count downstream.
    """
    match = _PARENTHETICAL.match(label.strip())
    if match is None:
        return None
    base = match.group("base").strip()
    qualifier = match.group("qualifier").strip()
    if not base or not qualifier:
        return None
    if any(character.isdigit() for character in qualifier):
        return None
    if fold(qualifier) == fold(base):
        return base  # pure repetition: "vox (vox)"
    base_tokens = [token for token in re.split(r"[\s\-]+", fold(base)) if token]
    if len(base_tokens) < 2:
        # A one-word name may still carry a redundant type: "vox (party)". Not "party (party)" or
        # "government (opposition)", where the bracket is the only thing that distinguishes it.
        if fold(base) in _GENERIC_BASES:
            return None
        return base if fold(qualifier) in _ORGANISATION_TYPES else None

    initials = "".join(token[0] for token in base_tokens)
    squashed = re.sub(r"[^a-z0-9]", "", fold(qualifier))
    if squashed and sorted(squashed) == sorted(initials):
        return base
    if fold(qualifier) in REDUNDANT_QUALIFIERS and any(
        token in _KEEP_IN_BASE for token in base_tokens
    ):
        return base
    return None


def display_form(raw: str) -> str:
    """The label a curator should see: whitespace collapsed, surrounding junk removed."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", raw)).strip(" \t\n\r,;:-")
