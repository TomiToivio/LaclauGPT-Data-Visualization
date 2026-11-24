"""Merge from the human-verified workbooks first (#311 / #315).

Tomi curated three workbooks by hand — `entities.xlsx`, `persons.xlsx`, `themes.xlsx`, each a two
column `old -> new` table. They outrank both the string matcher and the model panel: where a
workbook pair exists, that *is* the canonical name, verbatim, including the `(Party; Country)`
convention used for people.

So this module does the merge for those three categories, and reports exactly how much of the
corpus the human work covers — because "we used the workbooks" is only meaningful next to the
number of labels that had no workbook row and still rest on the matcher.
"""
from __future__ import annotations

import csv
import json
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKBOOK_FILES = {
    "entity": "entities.xlsx",
    "person": "persons.xlsx",
    "theme": "themes.xlsx",
}


@dataclass
class WorkbookMap:
    """One `old -> new` table, with the conflicts it contains kept visible."""

    category: str
    path: Path
    pairs: dict[str, str] = field(default_factory=dict)
    conflicts: dict[str, list[str]] = field(default_factory=dict)
    rows: int = 0
    empty_rows: int = 0

    def canonical(self, label: str) -> str:
        """The workbook's canonical name for a label, or the label itself."""
        return self.pairs.get(_key(label), label)

    def covers(self, label: str) -> bool:
        return _key(label) in self.pairs


def _key(label: str) -> str:
    """Match on the string a human typed: NFC, collapsed whitespace, case-folded."""
    return " ".join(unicodedata.normalize("NFC", str(label)).split()).casefold()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def read_workbook(path: Path, category: str) -> WorkbookMap:
    """Read a two-column `old -> new` sheet. Later rows never silently overwrite earlier ones."""
    if not path.exists():
        raise FileNotFoundError(f"workbook not found: {path}")
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        result = WorkbookMap(category=category, path=path)
        _ = header
        for old, new, *_ in rows:
            result.rows += 1
            old_text, new_text = _cell(old), _cell(new)
            if not old_text or not new_text:
                result.empty_rows += 1
                continue
            key = _key(old_text)
            previous = result.pairs.get(key)
            if previous is not None and previous != new_text:
                # The same spelling pointing at two names is a defect in the workbook, not
                # something to resolve by picking the last row.
                result.conflicts.setdefault(key, [previous]).append(new_text)
                continue
            result.pairs[key] = new_text
        return result
    finally:
        workbook.close()


def read_all(workbook_dir: Path) -> dict[str, WorkbookMap]:
    """The three workbooks, keyed by the category each one governs."""
    return {
        category: read_workbook(workbook_dir / filename, category)
        for category, filename in WORKBOOK_FILES.items()
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass
class WorkbookCluster:
    category: str
    canonical: str
    members: list[str]
    occurrences: int
    source: str  # "workbook" when a human row decided the name

    def as_row(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "canonical": self.canonical,
            "members": " | ".join(sorted(self.members)),
            "member_count": len(self.members),
            "occurrences": self.occurrences,
            "source": self.source,
        }


def merge_from_workbooks(
    run_dir: Path, workbooks: dict[str, WorkbookMap]
) -> tuple[dict[str, list[WorkbookCluster]], dict[str, Any]]:
    """Re-merge a run's labels for the workbook categories, and report coverage.

    The run contributes the occurrences — a human naming decision does not invent frequency. Every
    label the workbook knows joins its canonical name; every label it does not know keeps the
    name the matcher gave it, and is counted as uncovered so the gap is visible.
    """
    merged: dict[str, list[WorkbookCluster]] = {}
    coverage: dict[str, Any] = {}
    for category, workbook in workbooks.items():
        clusters: dict[str, WorkbookCluster] = {}
        covered = uncovered = 0
        seen: set[str] = set()

        def add(
            label: str,
            occurrences: int,
            canonical: str,
            source: str,
            *,
            clusters: dict[str, WorkbookCluster] = clusters,
            category: str = category,
        ) -> None:
            cluster = clusters.get(canonical)
            if cluster is None:
                clusters[canonical] = WorkbookCluster(
                    category=category, canonical=canonical, members=[label],
                    occurrences=occurrences, source=source,
                )
                return
            if label not in cluster.members:
                cluster.members.append(label)
            cluster.occurrences += occurrences
            if source == "workbook":
                cluster.source = "workbook"

        for row in _rows(run_dir / f"canonical_{category}.csv"):
            members = [item for item in row["members"].split(" | ") if item]
            occurrences = int(row["occurrences"] or 0)
            for member in members:
                if member in seen:
                    continue
                seen.add(member)
                if workbook.covers(member):
                    covered += 1
                    add(member, occurrences, workbook.canonical(member), "workbook")
                else:
                    uncovered += 1
                    add(member, occurrences, row["canonical"], "matcher")
        for row in _rows(run_dir / f"review_{category}.csv"):
            label = row["label"]
            if label in seen:
                continue
            seen.add(label)
            if workbook.covers(label):
                covered += 1
                add(label, int(row.get("occurrences") or 0), workbook.canonical(label), "workbook")

        merged[category] = sorted(clusters.values(), key=lambda item: (-item.occurrences, item.canonical))
        coverage[category] = {
            "labels": covered + uncovered,
            "covered_by_workbook": covered,
            "matcher_only": uncovered,
            "clusters": len(clusters),
            "workbook_rows": len(workbook.pairs),
            "workbook_conflicts": len(workbook.conflicts),
        }
    return merged, coverage


def merge_from_sources(
    pooled: dict[str, list[Any]],
    workbooks: dict[str, WorkbookMap],
    fallback: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, list[WorkbookCluster]], dict[str, Any]]:
    """Merge the *raw* corpus labels through the workbooks.

    This is the basis that matters: the workbooks were written against the raw spellings the
    extraction produces (`abir al-sahlani`, `afghanistan `), not against the matcher's tidied
    canonical names. Merging the matcher's output through them would mostly miss.
    """
    merged: dict[str, list[WorkbookCluster]] = {}
    coverage: dict[str, Any] = {}
    for category, workbook in workbooks.items():
        clusters: dict[str, WorkbookCluster] = {}
        covered = uncovered = 0
        matcher_names = (fallback or {}).get(category, {})
        for stat in pooled.get(category, []):
            is_covered = workbook.covers(stat.label)
            # A label the workbook does not know keeps the name the matcher already gave it —
            # otherwise every uncovered label becomes its own cluster and the merge is undone.
            canonical = (
                workbook.canonical(stat.label)
                if is_covered
                else matcher_names.get(stat.label.casefold(), stat.label)
            )
            covered += 1 if is_covered else 0
            uncovered += 0 if is_covered else 1
            cluster = clusters.get(canonical)
            if cluster is None:
                clusters[canonical] = WorkbookCluster(
                    category=category, canonical=canonical, members=[stat.label],
                    occurrences=stat.count, source="workbook" if is_covered else "matcher",
                )
            else:
                if stat.label not in cluster.members:
                    cluster.members.append(stat.label)
                cluster.occurrences += stat.count
                if is_covered:
                    cluster.source = "workbook"
        merged[category] = sorted(clusters.values(), key=lambda item: (-item.occurrences, item.canonical))
        coverage[category] = {
            "raw_labels": covered + uncovered,
            "covered_by_workbook": covered,
            "matcher_only": uncovered,
            "clusters": len(clusters),
            "workbook_rows": len(workbook.pairs),
            "workbook_conflicts": len(workbook.conflicts),
        }
    return merged, coverage


def write_release_tables(out_dir: Path, merged: dict[str, list[WorkbookCluster]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for category, clusters in merged.items():
        path = out_dir / f"canonical_{category}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["category", "canonical", "members", "member_count", "occurrences", "source"],
                lineterminator="\n",
            )
            writer.writeheader()
            for cluster in clusters:
                writer.writerow(cluster.as_row())


def describe(workbooks: dict[str, WorkbookMap]) -> dict[str, Any]:
    return {
        category: {
            "file": workbook.path.name,
            "rows_read": workbook.rows,
            "pairs": len(workbook.pairs),
            "empty_rows": workbook.empty_rows,
            "conflicts": len(workbook.conflicts),
            "sample_conflicts": dict(list(workbook.conflicts.items())[:5]),
        }
        for category, workbook in workbooks.items()
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Merge the workbook categories from the human tables.")
    parser.add_argument("--workbooks", required=True, help="directory holding the three xlsx files")
    parser.add_argument("--run", default="", help="a finished merge-lab run directory")
    parser.add_argument("--profile", default="", help="use the raw extraction instead of a run")
    parser.add_argument("--root", default="", help="private root for relative profile paths")
    parser.add_argument("--out", required=True, help="where to write canonical_<category>.csv")
    args = parser.parse_args(argv)

    workbooks = read_all(Path(args.workbooks).expanduser())
    if args.profile:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from ep24_merge_lab import sources

        loaded = sources.load_profile(
            Path(args.profile).expanduser(),
            root=Path(args.root).expanduser() if args.root else None,
        )
        pooled = sources.extract(loaded)
        merged, coverage = merge_from_sources(pooled, workbooks)
    elif args.run:
        merged, coverage = merge_from_workbooks(Path(args.run).expanduser(), workbooks)
    else:
        parser.error("give --profile (raw corpus) or --run (a finished run)")
    out_dir = Path(args.out).expanduser()
    write_release_tables(out_dir, merged)
    (out_dir / "workbook_coverage.json").write_text(
        json.dumps(
            {"workbooks": describe(workbooks), "coverage": coverage},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"workbooks": describe(workbooks), "coverage": coverage}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
