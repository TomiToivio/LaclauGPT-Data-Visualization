"""Researcher decisions, and the versioned output a run leaves behind (#300).

A merge is a research act, so every automatic decision has to be reversible and every manual one
has to survive the next run. Two files carry that:

``decisions.jsonl``
    Append-only. ``merge`` forces labels together, ``keep_separate`` forbids a pair outright,
    ``rename`` changes the display form without changing membership. Written by the CLI, read by
    every later run — which is what makes restart and resume safe.

``runs/<run-id>/``
    One directory per run: canonical tables, the alias map, the review queue, statistics and a
    manifest that names the exact input files by hash. Never overwritten, so an earlier curated
    version can always be re-exported or rolled back to.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .model import Cluster, LabelStat, MergeResult
from .similarity import RULES, CategoryRule, resolve

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers only
    from .workbook_mappings import WorkbookMappings

SCHEMA_VERSION = 1
ACTIONS = ("merge", "keep_separate", "rename")


@dataclass(frozen=True)
class Decision:
    """One researcher act. ``at``/``reviewer`` are left empty when the CLI did not set them."""

    category: str
    action: str
    canonical: str = ""
    members: tuple[str, ...] = ()
    reviewer: str = ""
    at: str = ""
    note: str = ""
    #: ``<session>:<action uid>`` when the decision came from the review UI, so re-committing a
    #: session cannot write the same decision twice.
    source_ref: str = ""

    def validate(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unknown decision action {self.action!r}; expected one of {ACTIONS}")
        if self.category not in RULES:
            raise ValueError(f"unknown category {self.category!r}")
        if self.action == "rename" and not self.canonical:
            raise ValueError("a rename decision needs a canonical name")
        if self.action == "merge" and len(self.members) < 2:
            raise ValueError("a merge decision needs at least two members")

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["members"] = list(self.members)
        return payload


def load_decisions(path: Path) -> list[Decision]:
    """Read the append-only log, refusing a malformed line rather than guessing at it."""
    if not path.exists():
        return []
    decisions: list[Decision] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number} is not valid JSON: {exc}") from exc
        decision = Decision(
            category=payload["category"],
            action=payload["action"],
            canonical=payload.get("canonical", ""),
            members=tuple(payload.get("members", ())),
            reviewer=payload.get("reviewer", ""),
            at=payload.get("at", ""),
            note=payload.get("note", ""),
            source_ref=payload.get("source_ref", ""),
        )
        decision.validate()
        decisions.append(decision)
    return decisions


def append_decision(path: Path, decision: Decision) -> None:
    decision.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision.as_json(), ensure_ascii=False, sort_keys=True) + "\n")


def decisions_for(decisions: Iterable[Decision], category: str) -> tuple[
    list[tuple[str, list[str]]], set[frozenset[str]], dict[str, str]
]:
    """Split the log into ``(forced merges, blocked pairs, renames)`` for one category."""
    forced: list[tuple[str, list[str]]] = []
    blocked: set[frozenset[str]] = set()
    renames: dict[str, str] = {}
    for decision in decisions:
        if decision.category != category:
            continue
        if decision.action == "merge":
            forced.append((decision.canonical or decision.members[0], list(decision.members)))
        elif decision.action == "keep_separate":
            members = list(decision.members) + ([decision.canonical] if decision.canonical else [])
            for index, left in enumerate(members):
                for right in members[index + 1 :]:
                    blocked.add(frozenset((left, right)))
        elif decision.action == "rename":
            for member in decision.members or (decision.canonical,):
                renames[member] = decision.canonical
    return forced, blocked, renames


def resolve_category(
    stats: list[LabelStat],
    category: str,
    decisions: Iterable[Decision] = (),
    *,
    rule: CategoryRule | None = None,
    workbook: WorkbookMappings | None = None,
) -> MergeResult:
    """Resolve one category with the researcher log and the human workbooks applied.

    ``rule`` overrides the category defaults. ``workbook`` carries the human-verified Excel
    mappings of #311: they are prepended to the researcher decisions, because a workbook row was
    a decision before this run existed, and their provenance is recorded as ``workbook`` rather
    than as a similarity method.
    """
    rule = rule or RULES[category]
    forced, blocked, renames = decisions_for(decisions, category)
    forced_methods: dict[str, str] = {}
    if workbook is not None:
        extra = workbook.forced.get(category) or []
        forced = [*extra, *forced]
        blocked = blocked | (workbook.blocked.get(category) or set())
        forced_methods = {canonical: "workbook" for canonical, _ in extra}
    result = resolve(stats, rule, forced=forced, blocked=blocked, forced_methods=forced_methods)
    if renames:
        result.clusters = [
            Cluster(
                canonical=renames.get(cluster.canonical, cluster.canonical),
                members=tuple(sorted(renames.get(member, member) for member in cluster.members)),
                confidence=cluster.confidence,
                method=cluster.method,
                count=cluster.count,
            )
            for cluster in result.clusters
        ]
    return result


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_run(
    out_dir: Path,
    *,
    results: dict[str, MergeResult],
    rule_overrides: dict[str, CategoryRule] | None = None,
    manifest_inputs: list[dict[str, object]] | None = None,
    profile_digest: str = "",
    registry: dict[str, object] | None = None,
    workbook: dict[str, object] | None = None,
    coverage: dict[str, object] | None = None,
    registry_aliases: dict[str, dict[str, list[dict[str, object]]]] | None = None,
    workbook_inputs: dict[str, object] | None = None,
) -> Path:
    """Write one immutable run directory and return its path."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs = out_dir / "runs"
    run_dir = runs / run_id
    suffix = 1
    while run_dir.exists():  # two runs inside one second must not overwrite each other
        run_dir = runs / f"{run_id}-{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=True)

    alias_rows: list[dict[str, object]] = []
    stats: dict[str, object] = {}
    for category, result in sorted(results.items()):
        clusters = sorted(result.clusters, key=lambda item: (-item.count, item.canonical))
        _write_csv(
            run_dir / f"canonical_{category}.csv",
            ["canonical", "members", "member_count", "occurrences", "confidence", "method"],
            [cluster.as_row() for cluster in clusters],
        )
        _write_csv(
            run_dir / f"review_{category}.csv",
            ["label", "occurrences", "alternatives", "reason"],
            [candidate.as_row() for candidate in result.candidates],
        )
        for cluster in clusters:
            for member in cluster.members:
                alias_rows.append(
                    {
                        "category": category,
                        "canonical": cluster.canonical,
                        "alias": member,
                        "occurrences": cluster.count,
                        "confidence": f"{cluster.confidence:.3f}",
                        "method": cluster.method,
                    }
                )
        stats[category] = {
            "labels_in": len(clusters) + len(result.singletons)
            + sum(len(cluster.members) - 1 for cluster in clusters),
            "clusters": len(clusters),
            "merged_labels": sum(len(cluster.members) for cluster in clusters),
            "singletons": len(result.singletons),
            "review_candidates": len(result.candidates),
        }

    _write_csv(
        run_dir / "alias_map.csv",
        ["category", "canonical", "alias", "occurrences", "confidence", "method"],
        sorted(alias_rows, key=lambda row: (row["category"], row["canonical"], row["alias"])),
    )
    # A registry rewrite collapses a corpus spelling into a canonical name; without this file the
    # alias it replaced exists nowhere in the run and the collapse cannot be audited or undone.
    if registry_aliases:
        registry_rows = [
            {
                "category": category,
                "canonical": canonical,
                "alias": str(item.get("alias", "")),
                "occurrences": int(str(item.get("occurrences", 0) or 0)),
                "polarity": item.get("polarity", ""),
                "countries": item.get("countries", []),
                "method": "registry",
            }
            for category, by_canonical in sorted(registry_aliases.items())
            for canonical, items in sorted(by_canonical.items())
            for item in items
        ]
        _write_csv(
            run_dir / "registry_aliases.csv",
            ["category", "canonical", "alias", "occurrences", "polarity", "countries", "method"],
            registry_rows,
        )
    if workbook:
        (run_dir / "workbook_mappings.json").write_text(
            json.dumps(workbook, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if coverage:
        (run_dir / "workbook_coverage.json").write_text(
            json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    (run_dir / "stats.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "categories": stats}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    outputs = {}
    for path in sorted(run_dir.glob("*.csv")) + sorted(run_dir.glob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        outputs[path.name] = {"sha256": digest, "bytes": path.stat().st_size}

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "created_at": datetime.now(UTC).isoformat(),
        "profile_sha256": profile_digest,
        # Which registry version produced this run: a result is only reproducible against a pin.
        "registry": registry or {"pinned": False},
        # The human workbooks are an input like any other, so their hashes belong in the manifest.
        "workbook": workbook_inputs or {"used": False},
        "inputs": manifest_inputs or [],
        "rules": {
            category: asdict(rule) for category, rule in sorted((rule_overrides or RULES).items())
        },
        "outputs": outputs,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    latest = out_dir / "LATEST"
    latest.write_text(run_dir.name + "\n", encoding="utf-8")
    return run_dir
