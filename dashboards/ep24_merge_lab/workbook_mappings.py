"""Human-verified Excel codebooks as the first input to merging (#311, section 8).

The three researcher workbooks are old-to-new tables. They are not evidence that a matcher may
re-derive; they are decisions, and a decision is applied before any similarity rule runs. Two
rules follow from that and are enforced here rather than elsewhere:

* **a human pair is a forced merge**, including its canonical spelling (party and country
  qualifiers included), and the run records which workbook, sheet and row produced it;
* **a contradiction is never resolved silently.** When the same alias points at two different
  canonical names, neither is applied: the alias goes to the adjudication queue and stays
  unresolved until a person decides.

Chains (``a -> b`` where ``b`` is itself an alias) are followed to the final target so a workbook
never produces a half-applied rename; a chain that closes on itself is a contradiction.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "ep24.workbook_mappings/1"

#: The workbook each merge category takes its human mappings from. Topics and sentiments have no
#: human workbook; they stay with the semantic review process.
WORKBOOK_CATEGORIES: dict[str, str] = {
    "entity": "entities.xlsx",
    "person": "persons.xlsx",
    "theme": "themes.xlsx",
}


@dataclass(frozen=True)
class Mapping:
    """One old-to-new row of a human workbook, with its provenance."""

    category: str
    alias: str
    canonical: str
    workbook: str
    sheet: str
    row: int

    def as_json(self) -> dict[str, object]:
        return {
            "category": self.category,
            "alias": self.alias,
            "canonical": self.canonical,
            "workbook": self.workbook,
            "sheet": self.sheet,
            "row": self.row,
        }


@dataclass
class WorkbookMappings:
    """What the workbooks force, what they leave open, and why."""

    #: category -> [(canonical, [members])], ready for ``similarity.resolve``.
    forced: dict[str, list[tuple[str, list[str]]]] = field(default_factory=dict)
    #: category -> canonical -> the workbook rows that produced it.
    provenance: dict[str, dict[str, list[dict[str, object]]]] = field(default_factory=dict)
    #: Contradictions a person has to settle; each carries every row that supports it.
    adjudication: list[dict[str, object]] = field(default_factory=list)
    #: Pairs of canonical names the workbooks keep apart, so no matcher may join them.
    blocked: dict[str, set[frozenset[str]]] = field(default_factory=dict)
    #: Human rows read, applied, skipped and refused, per category.
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_json(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "forced": {
                category: [
                    {"canonical": canonical, "members": members} for canonical, members in entries
                ]
                for category, entries in sorted(self.forced.items())
            },
            "provenance": {
                category: {canonical: rows for canonical, rows in sorted(by_canonical.items())}
                for category, by_canonical in sorted(self.provenance.items())
            },
            "adjudication": self.adjudication,
            "blocked": {
                category: sorted(sorted(pair) for pair in pairs)
                for category, pairs in sorted(self.blocked.items())
            },
            "counts": {category: dict(counts) for category, counts in sorted(self.counts.items())},
        }


def _fold(value: str) -> str:
    return " ".join(value.split()).casefold()


def _resolve_chain(
    start: str,
    index: dict[str, list[str]],
    *,
    category: str,
) -> tuple[str, list[str]] | None:
    """Follow ``a -> b -> c`` to its final canonical name, or report an ambiguous chain."""
    seen = [start]
    current = start
    last: str | None = None
    while True:
        # Two workbook rows for the same old label may differ only in spacing
        # ("politician  public figure" / "politician public figure"); that is one target, not an
        # ambiguous chain.
        unique: list[str] = []
        for target in index.get(current, []):
            if _fold(target) not in {_fold(existing) for existing in unique}:
                unique.append(target)
        if len(unique) != 1:
            break
        last = unique[0]
        following = _fold(last)
        if following == current:
            break
        if following in seen:
            return None
        seen.append(following)
        current = following
    if last is None:
        return None
    return last, seen


def from_evidence(evidence: dict, *, categories: tuple[str, ...] | None = None) -> WorkbookMappings:
    """Turn a ``workbook_evidence`` document into forced merges and an adjudication queue."""
    sources = evidence.get("sources") or {}
    wanted = categories or tuple(WORKBOOK_CATEGORIES)
    result = WorkbookMappings()

    for category in wanted:
        source = sources.get(category)
        if not source:
            continue
        workbook = str(source.get("file", WORKBOOK_CATEGORIES.get(category, "")))
        rows = source.get("pairs") or []
        #: folded alias -> every canonical spelling the workbook gives it
        index: dict[str, list[str]] = defaultdict(list)
        #: folded alias -> the rows the workbook actually wrote
        alias_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            alias = str(row.get("alias", "")).strip()
            canonical = str(row.get("canonical", "")).strip()
            if not alias or not canonical:
                continue
            provenance = {
                "workbook": workbook,
                "sheet": str(row.get("sheet", "")),
                "row": int(str(row.get("row", 0) or 0)),
            }
            index[_fold(alias)].append(canonical)
            alias_rows[_fold(alias)].append({"alias": alias, "canonical": canonical, **provenance})

        counts = {"rows": len(rows), "identity": 0, "applied": 0, "conflicting": 0, "cycles": 0}
        groups: dict[str, dict[str, object]] = {}
        for alias_key in sorted(index):
            targets = index[alias_key]
            distinct = sorted({_fold(target) for target in targets})
            written = {
                (str(row["alias"]), str(row["canonical"])) for row in alias_rows.get(alias_key, [])
            }
            if len(distinct) > 1:
                # Same old label, two different new labels: the workbook contradicts itself, so
                # neither mapping may be applied. A person settles it.
                counts["conflicting"] += 1
                result.adjudication.append(
                    {
                        "category": category,
                        "alias": alias_key,
                        "reason": "conflicting workbook targets",
                        "targets": targets,
                        "rows": alias_rows.get(alias_key, []),
                    }
                )
                continue
            if written and all(alias == canonical for alias, canonical in written):
                # "activism -> activism": the workbook agrees with the corpus spelling and says
                # nothing about membership. A case-only row ("afghanistan " -> "Afghanistan") is
                # *not* this case: it is a human naming decision and is applied below.
                counts["identity"] += 1
                continue
            chain = _resolve_chain(alias_key, index, category=category)
            if chain is None:
                counts["cycles"] += 1
                result.adjudication.append(
                    {
                        "category": category,
                        "alias": alias_key,
                        "reason": "workbook mappings form a cycle or an ambiguous chain",
                        "targets": targets,
                        "rows": alias_rows.get(alias_key, []),
                    }
                )
                continue
            canonical, path = chain
            key = _fold(canonical)
            group = groups.setdefault(
                key,
                {"canonical": canonical, "members": set(), "via": set()},
            )
            group["members"].add(alias_key)  # type: ignore[union-attr]
            if len(path) > 1:
                group["via"].update(path[:-1])  # type: ignore[union-attr]
            counts["applied"] += 1

        forced: list[tuple[str, list[str]]] = []
        by_canonical: dict[str, list[dict[str, object]]] = {}
        for key, group in sorted(groups.items()):
            canonical = str(group["canonical"])
            members = sorted({*group["members"], *group["via"]})  # type: ignore[arg-type]
            # The canonical itself is kept as the cluster name even when the corpus never writes
            # it: that is the whole point of a human-verified name. `resolve` maps corpus
            # spellings onto these members case-insensitively.
            forced.append((canonical, members))
            by_canonical[canonical] = [
                row for member in members for row in alias_rows.get(_fold(member), [])
            ]
        result.forced[category] = forced
        result.provenance[category] = by_canonical
        result.counts[category] = counts

        # Two canonical names that the workbook gives the same alias cannot both stand: already
        # reported above. Nothing else is pre-emptively blocked, because "keep separate" is a
        # human statement this file does not contain.
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    mappings = from_evidence(evidence)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(mappings.as_json(), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
