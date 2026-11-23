"""One canonical surface form per label, so a signifier is counted once.

Discourse analysis counts *signifiers*. "EU" and "European Union" are one actor, and counting
them apart splits that actor's standing in two — the bar chart reads 61 + 23 instead of 84, and
two rows compete in a ranking where one belongs. The same happens to "Safety"/"safety",
"The Guardian"/"Guardian" and "Open AI"/"OpenAI".

So this module folds variants that denote the same referent, and nothing else:

* whitespace, Unicode and trailing-punctuation variants;
* a leading article ("The Surveillance State" / "Surveillance State");
* case variants, resolved to a single surface form per corpus;
* acronyms and abbreviations with an uncontested expansion ("EU" -> "European Union").

It deliberately does **not** fold near-neighbours. "European Commission" is a different body
from the European Union, and "The Unchecked State" is a different imaginary from "The
Surveillance State"; merging those would delete a distinction, and in this project the
distinction is the data. An entry reaches :data:`ALIASES` only when the referent is the same,
which is why the table is short and written by hand.

The canonical surface form is chosen from the corpus, not asserted: the most frequent spelling
wins, tie-broken by the longer spelling and then alphabetically, so the result is deterministic
and usually the one a researcher would have typed. Whatever was folded is kept in
``frame.attrs["label_aliases"]`` so a count can always be traced back to its raw labels.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

__all__ = ["ALIASES", "LABEL_COLUMNS", "alias_key", "canonical_forms", "canonicalize_frame"]

#: Columns whose values are lists of discourse labels.
LABEL_COLUMNS = (
    "entities",
    "entity_mentions",
    "topics",
    "signifiers",
    "imaginaries",
    "nodal_points",
    "classifications",
    "discourses",
)

#: key (casefolded, article-stripped) -> canonical surface form.
#: Only same-referent pairs belong here. "EU Commission" is the Commission, not the Union.
ALIASES: dict[str, str] = {
    "eu": "European Union",
    "e.u.": "European Union",
    "european union (eu)": "European Union",
    "eu commission": "European Commission",
    "european commission (ec)": "European Commission",
    "eu parliament": "European Parliament",
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "un": "United Nations",
    "u.n.": "United Nations",
    "open ai": "OpenAI",
    "huggingface": "Hugging Face",
}


def _clean(label: Any) -> str:
    """Whitespace, Unicode and dangling-punctuation normalisation, without changing wording.

    Periods are kept: they are part of the abbreviation itself ("E.U.", "U.S.A.", "EU Inc."),
    and stripping one turns a known alias into an unknown label.
    """
    text = unicodedata.normalize("NFKC", str(label))
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" ,;:")


def _strip_article(text: str) -> str:
    """Drop a leading "The" when it is a naming convention rather than part of the phrase.

    "The Guardian" and "Guardian" are one newspaper: the article is how the masthead is written.
    "the system" is not "system" — there the article is part of the common noun phrase, and
    removing it changes the reading. So only a capitalised remainder is stripped.
    """
    head, _, tail = text.partition(" ")
    if head.casefold() != "the" or not tail:
        return text
    return tail if tail[:1].isupper() else text


def alias_key(label: Any) -> str:
    """Matching key for a label: cleaned, article-stripped, casefolded."""
    return _strip_article(_clean(label)).casefold()


def canonical_forms(labels: Iterable[Any]) -> dict[str, str]:
    """Map every label key seen in ``labels`` to its canonical surface form.

    Explicit :data:`ALIASES` always win. Everything else is resolved per corpus by frequency,
    ties broken by longer spelling then alphabetically, so two runs over the same data agree.
    """
    forms: dict[str, str] = dict(ALIASES)
    seen: dict[str, Counter[str]] = {}
    for label in labels:
        cleaned = _clean(label)
        if not cleaned:
            continue
        bare = _strip_article(cleaned)
        key = bare.casefold()
        if key in forms:
            continue
        seen.setdefault(key, Counter())[bare] += 1
    for key, counter in seen.items():
        forms[key] = sorted(counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0][0]
    return forms


def canonical_label(label: Any, forms: Mapping[str, str]) -> str:
    """Fold one label through ``forms``; unknown labels keep their own wording."""
    cleaned = _clean(label)
    if not cleaned:
        return ""
    bare = _strip_article(cleaned)
    return forms.get(bare.casefold()) or forms.get(cleaned.casefold()) or bare


def _canonical_sequence(values: Any, forms: Mapping[str, str]) -> list[Any]:
    """Canonicalise a label list, preserving order and dropping the duplicates folding creates."""
    if isinstance(values, str) or not isinstance(values, (list, tuple, set)):
        return values
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            out.append(value)  # e.g. an entity dict: not a label list member, leave it alone
            continue
        label = canonical_label(value, forms)
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


def canonicalize_frame(
    frame: pd.DataFrame, columns: Sequence[str] = LABEL_COLUMNS
) -> pd.DataFrame:
    """Fold label variants across a whole frame; the mapping lands in ``frame.attrs``.

    Corpus-wide on purpose: choosing a surface form needs to see every spelling, and the
    dashboard's frames are corpus-sized. The input frame is not mutated.
    """
    present = [column for column in columns if column in frame.columns]
    if frame.empty or not present:
        return frame
    forms = canonical_forms(label for column in present for values in frame[column] for label in _iter_labels(values))
    result = frame.copy()
    for column in present:
        result[column] = result[column].map(lambda values: _canonical_sequence(values, forms))
    result.attrs = {**frame.attrs, "label_aliases": _folded(forms)}
    return result


def _iter_labels(values: Any) -> Iterable[Any]:
    if isinstance(values, str) or not isinstance(values, (list, tuple, set)):
        return ()
    return (value for value in values if isinstance(value, str))


def _folded(forms: Mapping[str, str]) -> dict[str, str]:
    """The audit trail: raw spelling -> canonical spelling, only where they differ."""
    return {
        spelling: canonical
        for key, canonical in forms.items()
        for spelling in {key, key.title()}
        if spelling.casefold() != canonical.casefold()
    }
