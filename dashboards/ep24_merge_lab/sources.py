"""Adapters that read legacy EP24 label sources without assuming a private layout (#300).

The repository must not carry machine paths or a private source list, so a *profile* file — kept
in the private repository next to the data — names the files and the columns each category comes
from. This module is the only place that knows how to turn such a profile into labels.

Two shapes exist in the legacy corpus and both are supported:

``records``
    A per-record table (the legacy dashboards' dataframe) where each row carries comma- or
    newline-separated label lists: ``entities``, ``political_themes``, ``topics`` and the three
    polarity columns. Counts here are what the dashboards actually showed.

``codebook``
    A curated label table with ``label``, ``aliases`` and ``entity_type``. Entity rows are split
    into people and other entities by type, which is where the Persons category comes from.

Nothing in here writes, and nothing connects to a network or a database.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import CATEGORIES, LabelStat
from .normalization import normalize_label, redundant_qualifier

#: Profile authors write the column name ("entities"), the model has the category ("entity").
CATEGORY_ALIASES = {
    "entities": "entity",
    "entity": "entity",
    "persons": "person",
    "people": "person",
    "person": "person",
    "themes": "theme",
    "theme": "theme",
    "topics": "topic",
    "topic": "topic",
    "sentiments": "sentiment",
    "sentiment": "sentiment",
}

csv.field_size_limit(10**9)

_CSV_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1")


@dataclass(frozen=True)
class ListColumn:
    """One label list inside a record column."""

    column: str
    separator: str = ","
    #: ``sentiment`` entries carry the polarity of the column they came from.
    polarity: str = ""


@dataclass
class Source:
    """One file in the legacy corpus, and how to read labels out of it."""

    name: str
    kind: str
    path: Path
    encoding: str = "utf-8"
    #: ``records``: category -> column(s). ``codebook``: see the two ``*_COLUMN`` fields.
    lists: dict[str, list[ListColumn]] = field(default_factory=dict)
    label_column: str = "label"
    type_column: str = "entity_type"
    aliases_column: str = "aliases"
    country_column: str = ""
    #: Entity types that mean "a person" in a codebook. Everything else stays an entity.
    person_types: tuple[str, ...] = ("person",)


@dataclass
class Extraction:
    """Labels observed in one source, before they are pooled with the others."""

    source: str
    stats: dict[str, dict[tuple[str, str], LabelStat]] = field(default_factory=dict)
    rows: int = 0
    skipped: int = 0


def _open_text(path: Path, encoding: str) -> Any:
    try:
        return path.open("r", encoding=encoding, newline="")
    except UnicodeDecodeError:
        return path.open("r", encoding="latin-1", newline="")


def file_digest(path: Path) -> str:
    """sha256 of the file, so a run manifest can name exactly what it read."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_labels(value: Any, separator: str) -> list[str]:
    """Split a label list, tolerating the empty cells and stray separators legacy data has."""
    if value is None:
        return []
    text = str(value)
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    # A YAML/JSON profile may carry the escape (`"\\n"`) rather than the character, and both
    # mean "one label per line" to the person who wrote it.
    if separator in {"\n", "\\n"} or separator.endswith("\n"):
        parts = text.splitlines()
    elif len(separator) > 1 and not separator.startswith("\\"):
        # Several separators in one column: legacy exports mix ";" and "," in the same field, so a
        # single-character split silently keeps "a; b" as one label. Split on any of them.
        parts = re.split(f"[{re.escape(separator)}]", text)
    else:
        parts = text.split(separator)
    return [part.strip() for part in parts if part and part.strip() and part.strip().lower() != "nan"]


def split_aliases(value: Any) -> list[str]:
    """Aliases arrive comma-, semicolon- or newline-separated depending on the exporter."""
    if value is None:
        return []
    text = str(value)
    for separator in (";", ","):
        text = text.replace(separator, "\n")
    return split_labels(text, "\n")


def load_profile(path: Path, *, root: Path | None = None) -> list[Source]:
    """Read a JSON/YAML profile into `Source` objects, resolving paths against ``root``."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        document = yaml.safe_load(raw)
    else:
        document = json.loads(raw)
    sources: list[Source] = []
    for entry in document.get("sources", []):
        declared = Path(entry["path"])
        resolved = declared if declared.is_absolute() or root is None else (root / declared)
        lists: dict[str, list[ListColumn]] = {}
        for declared_category, config in (entry.get("lists") or {}).items():
            category = CATEGORY_ALIASES.get(declared_category, declared_category)
            if category not in CATEGORIES:
                raise ValueError(
                    f"source {entry['name']!r}: unknown category {declared_category!r}; "
                    f"use one of {sorted(CATEGORY_ALIASES)}"
                )
            if category == "sentiment":
                for polarity, spec in config.items():
                    lists.setdefault("sentiment", []).append(
                        ListColumn(
                            column=spec["column"],
                            separator=spec.get("separator", ","),
                            polarity=polarity,
                        )
                    )
            elif isinstance(config, list):
                lists[category] = [
                    ListColumn(column=item["column"], separator=item.get("separator", ","))
                    for item in config
                ]
            else:
                lists[category] = [
                    ListColumn(column=config["column"], separator=config.get("separator", ","))
                ]
        sources.append(
            Source(
                name=entry["name"],
                kind=entry["kind"],
                path=resolved,
                encoding=entry.get("encoding", "utf-8"),
                lists=lists,
                label_column=entry.get("label_column", "label"),
                type_column=entry.get("type_column", "entity_type"),
                aliases_column=entry.get("aliases_column", "aliases"),
                country_column=entry.get("country_column", ""),
                person_types=tuple(entry.get("person_types", ("person",))),
            )
        )
    return sources


def _add(
    extraction: Extraction,
    category: str,
    label: str,
    *,
    count: int = 1,
    country: str = "",
    polarity: str = "",
) -> None:
    """Accumulate one occurrence of a label under its (polarity-tagged) key."""
    key = (polarity, label)
    per_category = extraction.stats.setdefault(category, {})
    existing = per_category.get(key)
    countries = set(existing.countries) if existing else set()
    if country:
        countries.add(country)
    per_category[key] = LabelStat(
        label=label,
        count=(existing.count if existing else 0) + count,
        countries=tuple(sorted(countries)),
        polarity=polarity,
    )


def read_records(source: Source) -> Extraction:
    """Count every label list in a per-record table (the legacy dashboard dataframe)."""
    extraction = Extraction(source=source.name)
    with _open_text(source.path, source.encoding) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            extraction.rows += 1
            country = str(row.get(source.country_column) or "") if source.country_column else ""
            if not any(row.get(spec.column) for specs in source.lists.values() for spec in specs):
                extraction.skipped += 1
            for category, specs in source.lists.items():
                for spec in specs:
                    for label in split_labels(row.get(spec.column), spec.separator):
                        _add(
                            extraction,
                            category,
                            label,
                            country=country,
                            polarity=spec.polarity,
                        )
    return extraction


def read_codebook(source: Source, *, category: str) -> Extraction:
    """Count labels in a curated codebook table.

    ``category="person"`` keeps only rows whose type is a person type; ``category="entity"``
    keeps the rest, so the two categories partition the same table instead of overlapping.
    Aliases are counted too: a researcher who wrote *PM Orpo* somewhere must land on the same
    row as *Petteri Orpo*.
    """
    extraction = Extraction(source=source.name)
    aliases_category = "person" if category == "person" else "entity"
    with _open_text(source.path, source.encoding) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            extraction.rows += 1
            person = str(row.get(source.type_column) or "").strip() in source.person_types
            if person != (aliases_category == "person"):
                continue
            label = str(row.get(source.label_column) or "").strip()
            if not label:
                extraction.skipped += 1
                continue
            country = str(row.get(source.country_column) or "") if source.country_column else ""
            _add(extraction, category, label, count=1, country=country)
            for alias in split_aliases(row.get(source.aliases_column)):
                if alias and alias != label:
                    _add(extraction, category, alias, count=0, country=country)
    return extraction


def extract(sources: Iterable[Source], *, category: str | None = None) -> dict[str, list[LabelStat]]:
    """Pool the sources into ``category -> [LabelStat]``, summing counts across sources.

    Codebook sources are read once per category they can supply (entities split into people and
    non-people), so a table is never read twice for the same rows.
    """
    pooled: dict[str, dict[tuple[str, str], LabelStat]] = defaultdict(dict)
    for source in sources:
        if source.kind == "records":
            extractions = [read_records(source)]
        elif source.kind == "entity_codebook":
            extractions = [read_codebook(source, category="entity"), read_codebook(source, category="person")]
        elif source.kind == "topic_codebook":
            extractions = [read_codebook(source, category="topic")]
        else:
            raise ValueError(f"unknown source kind {source.kind!r} for {source.name!r}")
        for extraction in extractions:
            for found_category, stats in extraction.stats.items():
                bucket = pooled[found_category]
                for key, stat in stats.items():
                    existing = bucket.get(key)
                    if existing is None:
                        bucket[key] = stat
                    else:
                        bucket[key] = LabelStat(
                            label=stat.label,
                            count=existing.count + stat.count,
                            countries=tuple(sorted(set(existing.countries) | set(stat.countries))),
                            polarity=stat.polarity,
                        )
    result: dict[str, list[LabelStat]] = {}
    for found_category, stats in pooled.items():
        if category and found_category != category:
            continue
        collapsed = _collapse_redundant_qualifiers(stats)
        result[found_category] = sorted(collapsed.values(), key=lambda item: (-item.count, item.label))
    _move_person_labels(result)
    return result


def _collapse_redundant_qualifiers(
    stats: dict[tuple[str, str], LabelStat],
) -> dict[tuple[str, str], LabelStat]:
    """Fold "party (sdp)" into "party" before anything is clustered.

    Done here, on the pooled counts, so the collapsed spelling is what a researcher sees in the
    canonical table and what the dashboards would eventually count — not a merge the rules have to
    rediscover from two half-identical labels.
    """
    collapsed: dict[tuple[str, str], LabelStat] = {}
    for (polarity, label), stat in stats.items():  # keys are (polarity, label)
        base = redundant_qualifier(label)
        if base and base != label:
            stat = LabelStat(label=base, count=stat.count, countries=stat.countries, polarity=polarity)
            label = base
        key = (polarity, label)
        existing = collapsed.get(key)
        if existing is None:
            collapsed[key] = stat
        else:
            collapsed[key] = LabelStat(
                label=existing.label,
                count=existing.count + stat.count,
                countries=tuple(sorted(set(existing.countries) | set(stat.countries))),
                polarity=existing.polarity,
            )
    return collapsed


def _move_person_labels(result: dict[str, list[LabelStat]]) -> None:
    """Move record-level labels that name a known person out of the entity pool (#300).

    A legacy record column does not type its entities, so *Petteri Orpo* arrives as an entity
    even though the codebook says he is a person. Leaving him in both categories would count him
    twice in the review queue and split his aliases across two tabs. The codebook decides the
    boundary; the record occurrences follow the label to the person category, so the counts a
    researcher sees are the counts the dashboards showed.
    """
    persons = result.get("person") or []
    entities = result.get("entity") or []
    if not persons or not entities:
        return
    person_keys = {
        normalize_label(stat.label, strip_titles=True).key for stat in persons
    }
    extra: dict[str, int] = defaultdict(int)
    extra_countries: dict[str, set[str]] = defaultdict(set)
    remaining: list[LabelStat] = []
    for stat in entities:
        key = normalize_label(stat.label, strip_titles=True).key
        if key not in person_keys:
            remaining.append(stat)
            continue
        extra[key] += stat.count
        extra_countries[key].update(stat.countries)

    if extra:
        # The first person label for a key absorbs the counts; the other spellings that share
        # the key stay separate so the matcher can merge them on their own terms.
        absorbed: set[str] = set()
        merged: list[LabelStat] = []
        for stat in persons:
            key = normalize_label(stat.label, strip_titles=True).key
            if key in extra and key not in absorbed:
                absorbed.add(key)
                merged.append(
                    LabelStat(
                        label=stat.label,
                        count=stat.count + extra[key],
                        countries=tuple(sorted(set(stat.countries) | extra_countries[key])),
                        polarity=stat.polarity,
                    )
                )
            else:
                merged.append(stat)
        result["person"] = sorted(merged, key=lambda item: (-item.count, item.label))
    result["entity"] = remaining


def inventory(sources: Iterable[Source]) -> list[dict[str, Any]]:
    """Describe what is there before anything is merged: file, size, rows, distinct labels."""
    rows: list[dict[str, Any]] = []
    for source in sources:
        exists = source.path.exists()
        entry: dict[str, Any] = {
            "source": source.name,
            "kind": source.kind,
            "path": str(source.path),
            "exists": exists,
        }
        if not exists:
            rows.append(entry)
            continue
        entry["bytes"] = source.path.stat().st_size
        if source.kind == "records":
            extraction = read_records(source)
        elif source.kind == "entity_codebook":
            extraction = read_codebook(source, category="entity")
        else:
            extraction = read_codebook(source, category="topic")
        entry["rows"] = extraction.rows
        entry["skipped_rows"] = extraction.skipped
        entry["distinct_labels"] = {
            category: len(stats) for category, stats in sorted(extraction.stats.items())
        }
        rows.append(entry)
    return rows
