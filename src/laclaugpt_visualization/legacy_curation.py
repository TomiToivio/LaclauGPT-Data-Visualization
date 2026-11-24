"""Legacy EP24 curation: find and resolve labels that denote the same thing (issue #300).

The legacy EP24 exports spell one referent many ways — "Petteri Orpo", "Prime Minister Orpo",
"PM Orpo", "Orpo" — and every dashboard that counts those strings splits the actor. This module
proposes merges, with the category's own notion of sameness, and never decides silently:

    persons   identity. Titles and honorifics are not identity; a bare surname is only resolvable
              when exactly one full name owns it, otherwise it is a review candidate.
    entities  identity, plus acronym expansion ("EU" = "European Union" when the initials match).
    themes    equivalence, not relatedness: the token sets must match after folding separators and
    topics    plural/word order. "migration" and "migration policy" stay apart — related, not same.
    sentiments polarity. "positive" and "negative" are opposites and are never merged; only
              surface variants of one polarity fold.

Three guarantees the caller can rely on:

* **No unsafe transitive merges.** A cluster is only reported as resolved when every member matches
  the canonical form directly; a chain (A≈B, B≈C, A≉C) is demoted to review instead of collapsing.
* **Manual decisions win.** ``decisions.json`` in the working directory records confirmed merges and
  explicit keep-separates; a re-run honours them, so reviewing is not lost work.
* **The source is never rewritten.** Outputs are new canonical tables, an alias map, a review queue
  and statistics; the input file is opened read-only.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CATEGORIES",
    "Candidate",
    "CurationSettings",
    "cards",
    "curate",
    "normalise",
    "read_labels",
]

CATEGORIES = ("persons", "entities", "themes", "topics", "sentiments")

#: Honorifics and role words that qualify a person without identifying them.
TITLES = {
    "mr", "mrs", "ms", "dr", "prof", "president", "prime", "minister", "pm", "mep", "chairman",
    "chancellor", "senator", "secretary", "spokesperson", "candidate", "leader", "former", "vice",
}

#: Known cross-language and abbreviated names for the same referent (curated, grows by review).
ALIASES: dict[str, str] = {
    "suomi": "finland",
    "españa": "spain",
    "espana": "spain",
    "deutschland": "germany",
    "polska": "poland",
    "magyarország": "hungary",
    "magyarorszag": "hungary",
    "unkari": "hungary",
    "saksa": "germany",
    "ruotsi": "sweden",
    "ranska": "france",
    "eu": "european union",
    "e.u.": "european union",
    "european union eu": "european union",
    "us": "united states",
    "usa": "united states",
    "uk": "united kingdom",
    "un": "united nations",
}

#: One word per polarity. Opposites are never merged, only spelled one way.
SENTIMENT_FORMS: dict[str, str] = {
    "pos": "positive", "positive": "positive", "good": "positive", "favourable": "positive",
    "favorable": "positive", "supportive": "positive",
    "neg": "negative", "negative": "negative", "bad": "negative", "unfavourable": "negative",
    "unfavorable": "negative", "critical": "negative",
    "neu": "neutral", "neutral": "neutral", "none": "neutral", "mixed": "neutral",
}

POLARITY = {"positive": 1, "neutral": 0, "negative": -1}

SEPARATORS = re.compile(r"\s*[,;|/&]\s*")

#: Column names seen for each category across the legacy exports, first match wins.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "persons": ("persons", "person", "new_entity", "NER_politicians"),
    "entities": ("entities", "entity", "NER_entities"),
    "themes": ("themes", "theme", "new_theme", "political_themes"),
    "topics": ("topics", "topic", "lda_topic"),
    "sentiments": ("sentiments", "sentiment", "polarity"),
}

#: EP24 exports often carry polarity as three columns rather than as labels.
SENTIMENT_COLUMNS = ("positive", "neutral", "negative")


@dataclass(frozen=True)
class CurationSettings:
    """Thresholds. ``auto`` merges without review; ``review`` queues as a candidate."""

    auto: float = 0.95
    review: float = 0.70
    max_cluster: int = 40


@dataclass
class Candidate:
    canonical: str
    aliases: list[str]
    confidence: float
    method: str
    counts: dict[str, int] = field(default_factory=dict)
    needs_review: bool = False
    rationale: str = ""


def normalise(label: str, *, drop_titles: bool = False) -> str:
    """Case-, accent-, punctuation- and whitespace-insensitive form used for matching."""
    text = unicodedata.normalize("NFKD", str(label))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    words = [word for word in re.sub(r"\s+", " ", text).strip().split(" ") if word]
    if drop_titles:
        words = [word for word in words if word not in TITLES]
    return " ".join(words)


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _token_key(label: str) -> str:
    """Order-insensitive token key with plural folding, for themes and topics."""
    tokens = sorted(_singular(word) for word in normalise(label).split(" ") if word)
    return " ".join(tokens)


def read_labels(path: Path, category: str, *, delimiter: str = ",") -> Counter[str]:
    """Label -> occurrences for one category, read from a CSV (column = category) or JSON.

    The file is opened read-only: curation never edits its source.
    """
    path = Path(path)
    counts: Counter[str] = Counter()
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonl"}:
        rows = []
        with path.open(encoding="utf-8") as handle:
            if suffix == ".jsonl":
                rows = [json.loads(line) for line in handle if line.strip()]
            else:
                payload = json.load(handle)
                rows = payload if isinstance(payload, list) else payload.get("rows", [])
        for row in rows:
            counts.update(_cell_labels(row.get(category)))
        return counts

    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=delimiter))

    columns = set(rows[0].keys()) if rows else set()
    column = next((name for name in COLUMN_ALIASES.get(category, (category,)) if name in columns), None)
    if column is None and category == "sentiments" and set(SENTIMENT_COLUMNS) <= columns:
        # Polarity is encoded as columns: one label per non-empty cell. Already canonical, so the
        # sentiment tab is honest rather than empty.
        for polarity in SENTIMENT_COLUMNS:
            present = sum(1 for row in rows if str(row.get(polarity) or "").strip() not in {"", "nan", "none"})
            if present:
                counts[polarity] = present
        return counts
    if column is None:
        return counts

    for row in rows:
        counts.update(_cell_labels(row.get(column)))
    return counts


def _cell_labels(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    labels = []
    for part in SEPARATORS.split(text):
        label = re.sub(r"\s+", " ", part).strip(" .;:")
        if label and label.lower() not in {"nan", "none", "null"}:
            labels.append(label)
    return labels


def _person_surname(label: str) -> str:
    words = normalise(label, drop_titles=True).split(" ")
    return words[-1] if words else ""


def _acronym_matches(short: str, long: str) -> bool:
    initials = "".join(word[0] for word in long.split(" ") if word)
    return short.replace(".", "").replace(" ", "") == initials


def _candidates(counts: Counter[str], category: str, settings: CurationSettings) -> list[Candidate]:
    """Group labels of one category into candidates, with the category's own notion of sameness."""
    if category == "sentiments":
        return _sentiment_candidates(counts, settings)
    if category in {"themes", "topics"}:
        return _equivalence_candidates(counts, settings)
    return _identity_candidates(counts, category, settings)


def _identity_candidates(counts: Counter[str], category: str, settings: CurationSettings) -> list[Candidate]:
    """Persons and entities: same referent, judged from names, titles and acronyms."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for label in counts:
        key = ALIASES.get(normalise(label).replace(".", "."), None)
        if key is None:
            key = normalise(label, drop_titles=(category == "persons"))
            key = ALIASES.get(key, key)
        by_key[key].append(label)

    candidates: list[Candidate] = []
    for key, labels in by_key.items():
        if len(labels) == 1:
            continue
        best = max(labels, key=lambda label: (counts[label], len(label.split()), label))
        candidates.append(
            Candidate(
                canonical=best,
                aliases=sorted(labels, key=lambda label: -counts[label]),
                confidence=1.0,
                method="normalise+title-fold" if category == "persons" else "normalise+alias",
                counts={label: counts[label] for label in labels},
            )
        )

    # A bare surname is resolvable only when one full name owns it, and only for persons.
    if category == "persons":
        surnames: dict[str, list[str]] = defaultdict(list)
        for label in counts:
            words = normalise(label, drop_titles=True).split(" ")
            if len(words) >= 2:
                surnames.setdefault(words[-1], []).append(label)

        # Fold each bare-surname *group* ("Orpo", "PM Orpo") into the one full name that owns it.
        folded: list[str] = []
        for key, labels in list(by_key.items()):
            if len(key.split(" ")) != 1:
                continue
            owners = sorted(set(surnames.get(key, [])))
            if len(owners) == 1:
                owner = owners[0]
                merged_labels = labels + [owner]
                candidates = [
                    candidate for candidate in candidates
                    if candidate.canonical != max(labels, key=lambda label: (counts[label], len(label.split()), label))
                ]
                candidates.append(
                    Candidate(
                        canonical=owner,
                        aliases=sorted(merged_labels, key=lambda label: (-counts[label], label)),
                        confidence=0.96,
                        method="surname->full-name",
                        counts={label: counts[label] for label in merged_labels},
                        rationale=f"only {owner!r} carries this surname in the corpus",
                    )
                )
                folded.append(key)
        for key in folded:
            by_key.pop(key, None)

        for label in counts:
            if len(normalise(label, drop_titles=True).split(" ")) != 1:
                continue
            owners = sorted(set(surnames.get(_person_surname(label), [])))
            if len(owners) > 1:
                candidates.append(
                    Candidate(
                        canonical=label,
                        aliases=sorted(owners, key=lambda name: -counts[name]),
                        confidence=0.4,
                        method="ambiguous-surname",
                        counts={name: counts.get(name, 0) for name in owners},
                        needs_review=True,
                        rationale="several people share this surname; do not guess",
                    )
                )
    return candidates


def _equivalence_candidates(counts: Counter[str], settings: CurationSettings) -> list[Candidate]:
    """Themes and topics: equal token sets only — relatedness is not sameness."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for label in counts:
        by_key[_token_key(label)].append(label)

    candidates: list[Candidate] = []
    for labels in by_key.values():
        if len(labels) < 2:
            continue
        best = max(labels, key=lambda label: (counts[label], label))
        candidates.append(
            Candidate(
                canonical=best,
                aliases=sorted(labels, key=lambda label: -counts[label]),
                confidence=1.0,
                method="token-set-equality",
                counts={label: counts[label] for label in labels},
            )
        )
    return candidates


def _sentiment_candidates(counts: Counter[str], settings: CurationSettings) -> list[Candidate]:
    by_polarity: dict[str, list[str]] = defaultdict(list)
    for label in counts:
        key = normalise(label, drop_titles=True)
        canonical = SENTIMENT_FORMS.get(key, key)
        by_polarity[canonical].append(label)

    candidates: list[Candidate] = []
    for canonical, labels in by_polarity.items():
        if len(labels) < 2:
            continue
        best = max(labels, key=lambda label: (counts[label], label))
        candidates.append(
            Candidate(
                canonical=best,
                aliases=sorted(labels, key=lambda label: -counts[label]),
                confidence=1.0 if POLARITY.get(canonical) is not None else 0.9,
                method="polarity-form",
                counts={label: counts[label] for label in labels},
            )
        )
    return candidates


def _demote_chains(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Refuse transitive collapses: every alias must match the canonical on its own.

    A≈B and B≈C do not license A≈C. Any cluster that would rely on such a chain is demoted to
    review with the reason recorded, rather than silently merging distinct people or topics.
    """
    out: list[Candidate] = []
    for candidate in candidates:
        canonical_key = _token_key(candidate.canonical)
        direct = all(_token_key(alias) == canonical_key or alias == candidate.canonical for alias in candidate.aliases)
        if candidate.method in {
            "normalise+title-fold", "normalise+alias", "surname->full-name", "polarity-form",
            "ambiguous-surname",
        }:
            out.append(candidate)
            continue
        if direct:
            out.append(candidate)
        else:
            out.append(
                Candidate(
                    canonical=candidate.canonical,
                    aliases=candidate.aliases,
                    confidence=min(candidate.confidence, 0.5),
                    method=f"{candidate.method} (chain)",
                    counts=candidate.counts,
                    needs_review=True,
                    rationale="merging these would rely on a transitive chain of similarity",
                )
            )
    return out


def _apply_decisions(candidates: list[Candidate], decisions: dict[str, object]) -> list[Candidate]:
    """Honour recorded researcher decisions: merged groups and explicit keep-separates."""
    keep_separate = {normalise(item) for item in decisions.get("keep_separate", [])}
    forced = decisions.get("merge", {})
    out = []
    for candidate in candidates:
        if normalise(candidate.canonical) in keep_separate:
            continue
        alias_kept = [alias for alias in candidate.aliases if normalise(alias) not in keep_separate]
        if len(alias_kept) < len(candidate.aliases):
            candidate = Candidate(
                canonical=candidate.canonical,
                aliases=alias_kept,
                confidence=candidate.confidence,
                method=f"{candidate.method}+keep-separate",
                counts={alias: candidate.counts.get(alias, 0) for alias in alias_kept},
                needs_review=candidate.needs_review,
                rationale=candidate.rationale,
            )
        override = forced.get(candidate.canonical)
        if isinstance(override, str) and override.strip():
            target = override.strip()
            others = {candidate.canonical, *candidate.aliases} - {
                alias for alias in candidate.aliases if normalise(alias) == normalise(target)
            }
            others -= {target}
            candidate = Candidate(
                canonical=target,
                aliases=[target, *sorted(others, key=lambda label: (-candidate.counts.get(label, 0), label))],
                confidence=1.0,
                method=f"{candidate.method}+manual",
                counts=candidate.counts,
            )
        out.append(candidate)
    return out


def cards(
    category: str,
    counts: Counter[str],
    result: dict[str, object],
    *,
    unresolved_limit: int = 60,
) -> list[dict[str, object]]:
    """Board cards for one category: proposals first, then confirmed clusters, then loose labels.

    Loose labels are the point. A category where the rule proposed nothing still has labels, and a
    board that draws only clusters shows an empty tab that reads as "no data".
    """
    rows: list[dict[str, object]] = []
    for row in result["review"]:  # type: ignore[union-attr]
        if row["category"] != category:
            continue
        labels = [item.strip() for item in str(row["candidates"]).split(";") if item.strip()]
        rows.append({
            "id": f"review::{row['proposed_canonical']}",
            "label": row["proposed_canonical"],
            "aliases": labels,
            "count": sum(counts.get(label, 0) for label in labels),
            "confidence": float(row["confidence"]),
            "status": "review",
            "rationale": row["rationale"],
        })
    for row in result["canonical"]:  # type: ignore[union-attr]
        if row["category"] != category:
            continue
        rows.append({
            "id": f"merged::{row['canonical']}",
            "label": row["canonical"],
            "aliases": [item.strip() for item in str(row["aliases"]).split(";") if item.strip()],
            "count": int(row["occurrences"]),
            "confidence": float(row["confidence"]),
            "status": "merged",
            "rationale": row["method"],
        })

    clustered = {label for row in rows for label in row["aliases"]}
    loose = sorted(
        ((label, count) for label, count in counts.items() if label not in clustered),
        key=lambda item: (-item[1], item[0]),
    )
    for label, count in loose[:unresolved_limit]:
        rows.append({
            "id": f"label::{label}",
            "label": label,
            "aliases": [],
            "count": int(count),
            "confidence": 1.0,
            "status": "unresolved",
            "rationale": "not merged by any rule — drag onto another card to merge by hand",
        })
    return sorted(rows, key=lambda row: (-len(row["aliases"]), -int(row["count"])))


def curate(
    labelled: dict[str, Counter[str]],
    *,
    settings: CurationSettings | None = None,
    decisions: dict[str, object] | None = None,
) -> dict[str, object]:
    """Propose merges per category and return tables, queue and statistics (no files written)."""
    settings = settings or CurationSettings()
    decisions = decisions or {}

    canonical_rows: list[dict[str, object]] = []
    alias_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    stats: dict[str, object] = {}

    for category, counts in labelled.items():
        candidates = _demote_chains(_candidates(counts, category, settings))
        candidates = _apply_decisions(candidates, decisions)
        auto = [c for c in candidates if not c.needs_review and c.confidence >= settings.auto]
        review = [c for c in candidates if c not in auto]

        for candidate in auto:
            canonical_rows.append(
                {
                    "category": category,
                    "canonical": candidate.canonical,
                    "aliases": "; ".join(candidate.aliases),
                    "occurrences": sum(candidate.counts.values()),
                    "confidence": round(candidate.confidence, 3),
                    "method": candidate.method,
                }
            )
            for alias in candidate.aliases:
                alias_rows.append(
                    {
                        "category": category,
                        "alias": alias,
                        "canonical": candidate.canonical,
                        "occurrences": candidate.counts.get(alias, 0),
                        "confidence": round(candidate.confidence, 3),
                        "method": candidate.method,
                    }
                )
        for candidate in review:
            review_rows.append(
                {
                    "category": category,
                    "proposed_canonical": candidate.canonical,
                    "candidates": "; ".join(candidate.aliases),
                    "occurrences": sum(candidate.counts.values()),
                    "confidence": round(candidate.confidence, 3),
                    "method": candidate.method,
                    "rationale": candidate.rationale,
                }
            )

        merged_occurrences = sum(sum(c.counts.values()) - c.counts.get(c.canonical, 0) for c in auto)
        stats[category] = {
            "labels": len(counts),
            "auto_merges": len(auto),
            "review_candidates": len(review),
            "labels_collapsed": sum(len(c.aliases) - 1 for c in auto),
            "occurrences_folded": merged_occurrences,
            "distinct_after": len(counts) - sum(len(c.aliases) - 1 for c in auto),
        }

    return {
        "canonical": canonical_rows,
        "aliases": alias_rows,
        "review": review_rows,
        "stats": stats,
    }


def write_outputs(result: dict[str, object], out_dir: Path, *, dry_run: bool = False) -> dict[str, str]:
    """Write canonical tables, alias map, review queue and statistics; return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    if dry_run:
        return paths

    import csv

    def dump(name: str, rows: object) -> None:
        path = out_dir / name
        rows = list(rows) if isinstance(rows, Iterable) else rows
        fieldnames = list(rows[0].keys()) if rows else []
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        paths[name] = str(path)

    dump("canonical.csv", result["canonical"])
    dump("aliases.csv", result["aliases"])
    dump("review_queue.csv", result["review"])
    stats_path = out_dir / "summary.json"
    stats_path.write_text(json.dumps(result["stats"], indent=2, sort_keys=True), encoding="utf-8")
    paths["summary.json"] = str(stats_path)
    return paths
