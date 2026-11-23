"""Merge PLEDGE labels that mean the same thing — corpus-driven, not a guess list.

The first version of this module folded a curated handful and left 330 of the corpus's 331
same-meaning groups split. The audit showed the classes, and they are mechanical, so the rule is
now derived from the data rather than enumerated by hand:

    the european union (195) / european union (1561)      leading article
    european union (eu) (23) / european union (1561)     disambiguating parenthesis
    pedro sánchez (180) / pedro sanchez (6)              accents
    viktor orbán (69) / viktor orban (2)                 accents
    karacsony_gergely (5) / karácsony gergely (88)       punctuation
    influencer (34) / influencers (83)                   singular / plural
    vox party (66) / vox (280)                           trailing "party"

Groups are formed by a match key (accents, case, punctuation, articles and *qualifying*
parentheses removed); the surface form kept is the group's most frequent spelling, so the accented
and correctly written variant wins. Plural and "party" folds are applied only when both forms
actually occur, which is why "politics" is never touched.

What stays apart, deliberately: parentheses that name a **different** referent
("government (of spain)" vs "government (france)"), and institutions that merely sound alike
(european commission / european union / european unity).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping

__all__ = ["MERGE_MAP", "build_forms", "merge_cell", "merge_labels", "split_cell"]

#: Separators between tags in one cell.
SEPARATORS = re.compile(r"\s*[,;|]\s*")

#: Parenthetical content that qualifies the *same* referent rather than naming a different one.
QUALIFIERS = {
    "implicit", "implied", "explicit", "general", "contextual", "collective", "unspecified",
    "potential", "satirical", "critique", "superficial", "hypothetical", "rhetorical", "ironic",
    "unidentified", "unnamed", "inferred", "mentioned", "referenced", "abstract",
}

#: Parenthetical types: what the entity *is*, not another entity.
TYPE_WORDS = {"political party", "party", "politician", "politicians", "person", "actor", "institution"}

#: Synonyms with one referent that no mechanical rule can derive.
MERGE_MAP: dict[str, str] = {
    "eu": "european union",
    "e.u.": "european union",
    "european union eu": "european union",
    "eu european union": "european union",
    "eu commission": "european commission",
    "european commission eu": "european commission",
    "eu parliament": "european parliament",
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


def _deaccent(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _strip_parenthetical(label: str) -> str:
    """Drop a trailing parenthesis that qualifies the same referent, keep one that names another.

    ``vox (political party)`` and ``european union (eu)`` qualify: the parenthesis is a type or an
    acronym of the same thing. ``government (of spain)`` and ``spanish government (moncloa)`` do
    not: stripping the second would fold the Spanish government into a generic "government", and
    stripping the first would fold two different governments together.
    """
    match = re.match(r"^(?P<base>.*?)\s*\((?P<inner>[^()]*)\)\s*$", label)
    if not match:
        return label
    base, inner = match.group("base").strip(), match.group("inner").strip().casefold()
    if not base:
        return label
    if inner in QUALIFIERS or inner in TYPE_WORDS:
        return base
    # An acronym of the base ("european union (eu)", "united states (us)").
    initials = "".join(word[0] for word in re.findall(r"[A-Za-zÀ-ÿ]+", base)).casefold()
    squashed = re.sub(r"[^a-z]", "", inner)
    if squashed and (squashed == initials or base.casefold().endswith(inner)):
        return base
    return label


def match_key(label: str) -> str:
    """The same-meaning key: accent-, case-, punctuation-, article- and qualifier-insensitive."""
    text = _strip_parenthetical(re.sub(r"\s+", " ", str(label)).strip())
    text = _deaccent(text).casefold()
    # "/" and "&" are separators, not meaning: "populism/anti-establishment sentiment" and
    # "populism & anti-establishment sentiment" are the same topic.
    text = re.sub(r"[^a-z0-9\s]", " ", text.replace("&", " ").replace("/", " "))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^the ", "", text)


def build_forms(values: Iterable[object]) -> dict[str, str]:
    """Learn the canonical surface form per same-meaning key from the whole column.

    Frequency decides, so the correctly spelled and accented variant wins; ties go to the longer
    spelling and then alphabetically, so two runs over the same data agree.
    """
    counts: Counter[str] = Counter()
    for value in values:
        counts.update(split_cell(value))

    spellings: dict[str, Counter[str]] = {}
    for label, count in counts.items():
        spellings.setdefault(match_key(label), Counter())[_strip_parenthetical(label)] += count

    # MERGE_MAP is written the way a human writes a synonym; forms are keyed by match_key.
    forms = {match_key(source): target for source, target in MERGE_MAP.items()}
    for key, counter in spellings.items():
        if key in forms:
            continue
        forms[key] = min(counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0]

    # Singular/plural: fold the rarer form into the commoner one — only when both exist.
    for key in sorted(spellings, key=lambda k: -sum(spellings[k].values())):
        if not key.endswith("s") or key.endswith("ss") or key[:-1] not in forms:
            continue
        plural_weight = sum(spellings[key].values())
        singular_weight = sum(spellings[key[:-1]].values())
        if plural_weight > singular_weight:
            forms[key[:-1]] = forms[key]
        else:
            forms[key] = forms[key[:-1]]

    # Trailing "party": "vox party" is "vox" — but only when the bare form is in the corpus.
    for key in list(forms):
        bare = key.removesuffix(" party").removesuffix(" political party")
        if bare != key and bare in forms:
            forms[key] = forms[bare]

    return forms


def merge_labels(labels: Iterable[str], forms: Mapping[str, str] | None = None) -> list[str]:
    """Fold a label sequence through ``forms``, dedupe, keep first-seen order.

    Without ``forms`` the curated synonyms and the mechanical key still apply, which is what a
    single cell can do on its own.
    """
    forms = forms if forms is not None else {match_key(source): target for source, target in MERGE_MAP.items()}
    merged: list[str] = []
    for label in labels:
        key = match_key(label)
        canonical = forms.get(key) or _strip_parenthetical(label).strip()
        canonical = re.sub(r"^the ", "", canonical, flags=re.IGNORECASE) or canonical
        if canonical.casefold() not in {item.casefold() for item in merged}:
            merged.append(canonical)
    return merged


def merge_cell(value: object, forms: Mapping[str, str] | None = None) -> str:
    """Merge one comma-joined cell: ``"the european union eu, politician"`` ->
    ``"european union, politicians"``."""
    return ", ".join(merge_labels(split_cell(value), forms))
