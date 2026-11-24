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


def clean_label(text: str) -> str:
    """Remove redundant parenthetical annotations and leading articles."""
    value = unicodedata.normalize("NFC", text).strip()
    while re.search(r"\([^()]*\)", value):
        value = re.sub(r"\([^()]*\)", " ", value)
    value = re.sub(r"\([^)]*$", "", value)
    value = _SPACE.sub(" ", value.replace(")", " ")).strip(" ,;:-")
    value = re.sub(r"^the\s+", "", value, flags=re.IGNORECASE)
    return value.strip() or text.strip()


def fold(text: str) -> str:
    """Unicode-normalize, case-fold, and collapse the whitespace/punctuation extractors add."""
    normalized = unicodedata.normalize("NFKC", clean_label(text)).translate(_TRANSLATION).casefold()
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
) -> Normalized:
    """Fold one label and, where the category allows it, drop words that carry no identity.

    ``strip_titles`` is for people (``PM Orpo`` -> ``orpo``) and ``strip_legal_suffixes`` for
    organisations (``Fortum Oyj`` -> ``fortum``). Neither is applied to themes, topics or
    sentiment targets, where every word can carry meaning.
    """
    folded = fold(raw)
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


def display_form(raw: str) -> str:
    """The label a curator should see: whitespace collapsed, surrounding junk removed."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", raw)).strip(" \t\n\r,;:-")
