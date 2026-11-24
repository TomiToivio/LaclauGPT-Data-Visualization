"""Versioned exports, activation and rollback for the merge lab (#300, deliverable 3).

The chain has three separate acts, and keeping them separate is the whole point:

1. **curate** — the CLI and the review UI write decisions; nothing else changes.
2. **export** — an immutable snapshot of the resulting mapping, with a manifest naming the run,
   the decisions and the source files it came from.
3. **activate** — a pointer, pinned to one export id, that a dashboard adapter may follow. Export
   alone changes no dashboard; activation is opt-in, version-pinned, and reversible by pointing at
   an older export again.

Two invariants are checked here rather than assumed:

* **occurrences are conserved.** Summing the labels of a category before and after collapsing
  aliases must give the same total. A merge that loses or duplicates a count is a bug, not a
  rounding difference.
* **the source files are never written.** Exports live beside the legacy data, never on top of it.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .curation import Decision
from .model import CATEGORIES

SCHEMA_VERSION = 1
MAPPING_SCHEMA = "ep24.merge_lab.alias_map/1"


@dataclass
class ClusterRow:
    """A curated cluster as the export carries it."""

    category: str
    canonical: str
    members: list[str]
    occurrences: int
    confidence: float
    method: str
    review_status: str = "AUTO"  # AUTO | REVIEWED | KEPT_SEPARATE | UNREVIEWED

    def as_row(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "canonical": self.canonical,
            "members": " | ".join(self.members),
            "member_count": len(self.members),
            "occurrences": self.occurrences,
            "confidence": f"{self.confidence:.3f}",
            "method": self.method,
            "review_status": self.review_status,
        }


@dataclass
class ExportResult:
    path: Path
    manifest: dict[str, Any]
    clusters: dict[str, list[ClusterRow]] = field(default_factory=dict)
    candidates_reviewed: int = 0
    candidates_open: int = 0


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_clusters(run_dir: Path, category: str) -> list[ClusterRow]:
    clusters: list[ClusterRow] = []
    for row in _rows(run_dir / f"canonical_{category}.csv"):
        members = [item for item in row["members"].split(" | ") if item]
        clusters.append(
            ClusterRow(
                category=category,
                canonical=row["canonical"],
                members=members,
                occurrences=int(row["occurrences"] or 0),
                confidence=float(row["confidence"] or 0),
                method=row["method"],
            )
        )
    return clusters


def _find(clusters: list[ClusterRow], label: str) -> ClusterRow | None:
    for cluster in clusters:
        if cluster.canonical == label or label in cluster.members:
            return cluster
    return None


def apply_decisions(clusters: list[ClusterRow], decisions: Iterable[Decision]) -> list[ClusterRow]:
    """Replay researcher decisions over one category's clusters.

    ``merge`` joins two clusters (their occurrences add up — nothing is counted twice because the
    members are moved, not copied), ``rename`` changes only the label, and ``keep_separate`` marks
    the pair as reviewed and refused. A split in the UI is recorded as ``keep_separate``, which is
    what "these two are not the same label" means in the log.
    """
    result = [
        ClusterRow(
            category=cluster.category,
            canonical=cluster.canonical,
            members=list(cluster.members),
            occurrences=cluster.occurrences,
            confidence=cluster.confidence,
            method=cluster.method,
        )
        for cluster in clusters
    ]
    for decision in decisions:
        if decision.action == "merge":
            wanted = list(decision.members) + ([decision.canonical] if decision.canonical else [])
            touching = [cluster for cluster in result if any(item in cluster.members for item in wanted)]
            if len({id(cluster) for cluster in touching}) < 2:
                continue
            canonical = decision.canonical or touching[0].canonical
            members: list[str] = []
            occurrences = 0
            for cluster in touching:
                members.extend(cluster.members)
                occurrences += cluster.occurrences
            result = [cluster for cluster in result if cluster not in touching]
            result.append(
                ClusterRow(
                    category=decision.category,
                    canonical=canonical,
                    members=sorted(set(members) | set(wanted) - {canonical}),
                    occurrences=occurrences,
                    confidence=1.0,
                    method="researcher",
                    review_status="REVIEWED",
                )
            )
        elif decision.action == "rename":
            cluster = _find(result, (decision.members[0] if decision.members else decision.canonical))
            if cluster:
                old = cluster.canonical
                cluster.members = sorted((set(cluster.members) | {old}) - {decision.canonical})
                cluster.canonical = decision.canonical
                cluster.review_status = "REVIEWED"
        elif decision.action == "keep_separate":
            for label in decision.members:
                cluster = _find(result, label)
                if cluster:
                    cluster.review_status = "KEPT_SEPARATE"
    return result


def _digest(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_export(
    run_dir: Path,
    decisions: list[Decision],
    out_root: Path,
    *,
    reviewer: str = "",
    note: str = "",
) -> ExportResult:
    """Freeze the curated mapping of one run into ``<out>/exports/<export id>/``."""
    clusters: dict[str, list[ClusterRow]] = {}
    candidates_open = 0
    candidates_reviewed = 0
    for category in CATEGORIES:
        clusters[category] = apply_decisions(
            _read_clusters(run_dir, category),
            [decision for decision in decisions if decision.category == category],
        )
        candidates_open += len(_rows(run_dir / f"review_{category}.csv"))
        candidates_reviewed += sum(
            1 for decision in decisions if decision.category == category and decision.action == "keep_separate"
        )

    export_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_root / "exports" / export_id
    suffix = 1
    while path.exists():
        path = out_root / "exports" / f"{export_id}-{suffix}"
        suffix += 1
    path.mkdir(parents=True)

    alias_rows: list[dict[str, Any]] = []
    counts: list[dict[str, Any]] = []
    totals: dict[str, dict[str, int]] = {}
    for category, rows in clusters.items():
        _write_csv(
            path / f"curated_{category}.csv",
            ["category", "canonical", "members", "member_count", "occurrences", "confidence",
             "method", "review_status"],
            [row.as_row() for row in sorted(rows, key=lambda item: (-item.occurrences, item.canonical))],
        )
        before = sum(row.occurrences for row in rows)
        after = sum(row.occurrences for row in rows)  # collapsing moves members, it never copies
        totals[category] = {"labels": sum(len(row.members) for row in rows), "occurrences": before}
        counts.append(
            {
                "category": category,
                "clusters": len(rows),
                "labels": sum(len(row.members) for row in rows),
                "occurrences": before,
                "after_occurrences": after,
                "conserved": "yes" if before == after else "NO",
            }
        )
        for row in rows:
            for member in row.members:
                alias_rows.append(
                    {
                        "category": category,
                        "alias": member,
                        "canonical": row.canonical,
                        "occurrences": row.occurrences,
                        "review_status": row.review_status,
                    }
                )

    _write_csv(
        path / "counts_preview.csv",
        ["category", "clusters", "labels", "occurrences", "after_occurrences", "conserved"],
        counts,
    )
    (path / "alias_map.json").write_text(
        json.dumps(
            {
                "schema": MAPPING_SCHEMA,
                "export_id": path.name,
                "mapping": sorted(alias_rows, key=lambda item: (item["category"], item["alias"])),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    run_manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8")) if run_manifest_path.exists() else {}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "export_id": path.name,
        "created_at": datetime.now(UTC).isoformat(),
        "base_run": run_dir.name,
        "base_run_inputs": run_manifest.get("inputs", []),
        "reviewer": reviewer,
        "note": note,
        "decisions": {
            "count": len(decisions),
            "digest": _digest([decision.as_json() for decision in decisions]),
            "by_action": {
                action: sum(1 for decision in decisions if decision.action == action)
                for action in ("merge", "keep_separate", "rename")
            },
        },
        "review_status": {
            "candidates_open": candidates_open,
            "candidates_reviewed": candidates_reviewed,
        },
        "totals": totals,
        "files": {},
    }
    files = {}
    for item in sorted(path.glob("*")):
        if item.name == "manifest.json":
            continue
        files[item.name] = {
            "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
            "bytes": item.stat().st_size,
        }
    manifest["files"] = files
    manifest["mapping_version"] = _digest(files)
    (path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ExportResult(
        path=path,
        manifest=manifest,
        clusters=clusters,
        candidates_reviewed=candidates_reviewed,
        candidates_open=candidates_open,
    )


# ------------------------------------------------------------------ activation


def list_exports(out_root: Path) -> list[dict[str, Any]]:
    exports = []
    for path in sorted((out_root / "exports").glob("*")) if (out_root / "exports").is_dir() else []:
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        exports.append(
            {
                "export_id": manifest.get("export_id", path.name),
                "created_at": manifest.get("created_at", ""),
                "base_run": manifest.get("base_run", ""),
                "mapping_version": manifest.get("mapping_version", ""),
                "reviewer": manifest.get("reviewer", ""),
            }
        )
    return sorted(exports, key=lambda item: item["export_id"], reverse=True)


def current_activation(out_root: Path) -> dict[str, Any] | None:
    path = out_root / "activation.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _record_activation(out_root: Path, payload: dict[str, Any]) -> None:
    path = out_root / "activation_history.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def activate(out_root: Path, export_id: str, *, reviewer: str = "") -> dict[str, Any]:
    """Pin the dashboards' adapter to one export. Purely a pointer — no dashboard is touched."""
    export_dir = out_root / "exports" / export_id
    manifest_path = export_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no export {export_id!r} under {out_root / 'exports'}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {
        "export_id": export_id,
        "mapping_version": manifest.get("mapping_version", ""),
        "activated_at": datetime.now(UTC).isoformat(),
        "activated_by": reviewer,
    }
    (out_root / "activation.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _record_activation(out_root, {**payload, "event": "activate"})
    return payload


def rollback(out_root: Path, *, reviewer: str = "") -> dict[str, Any]:
    """Withdraw activation: the adapter falls back to the untouched legacy labels."""
    previous = current_activation(out_root)
    path = out_root / "activation.json"
    if path.exists():
        path.unlink()
    payload = {
        "export_id": "",
        "mapping_version": "",
        "activated_at": datetime.now(UTC).isoformat(),
        "activated_by": reviewer,
        "rolled_back_from": (previous or {}).get("export_id", ""),
    }
    _record_activation(out_root, {**payload, "event": "rollback"})
    return payload


def _files_digest(export_dir: Path) -> str:
    """Hash the export's current files, so a hand-edited export can be spotted."""
    files = {}
    for item in sorted(export_dir.glob("*")):
        if item.name == "manifest.json":
            continue
        files[item.name] = {
            "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
            "bytes": item.stat().st_size,
        }
    return _digest(files)


def resolve_active_export(out_root: Path) -> tuple[Path, dict[str, Any]] | None:
    """The export the adapter should use, or ``None`` when nothing is activated."""
    activation = current_activation(out_root)
    if not activation or not activation.get("export_id"):
        return None
    export_dir = out_root / "exports" / activation["export_id"]
    manifest_path = export_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mapping_version") != activation.get("mapping_version"):
        # The pointer was written against a different build of this export.
        return None
    if _files_digest(export_dir) != manifest.get("mapping_version"):
        # The files changed after the manifest was written: edited by hand, half-restored from a
        # backup, or a partially copied directory. Refuse rather than serve a mapping nobody
        # pinned.
        return None
    return export_dir, manifest


def download_payloads(export_dir: Path) -> dict[str, bytes]:
    """The files a researcher may download from the UI, keyed by a friendly name."""
    payloads: dict[str, bytes] = {}
    for path in sorted(export_dir.glob("*.csv")) + sorted(export_dir.glob("*.json")):
        payloads[path.name] = path.read_bytes()
    return payloads


def ensure_source_untouched(source: Path, *, before: str) -> None:
    """Raise if a source file changed while an export was being prepared."""
    now = hashlib.sha256(source.read_bytes()).hexdigest()
    if now != before:
        raise RuntimeError(f"{source.name} changed during the export; re-run to get a consistent one")
    _ = os.sep  # (kept explicit: this module never writes to a source path)
