"""Child tables of the checkpoint export: entities, themes, DNA statements, SNA nodes and edges.

The delivered export (`analysis/ep24/pouta_exports/fiplpt_500_*/`) keeps one row per video in
`combined.csv` and the one-to-many findings in normalised child tables, keyed by `source_key`. The
researcher app was written for the *other* dialect, where those findings sit inside the parent row as
JSON columns (`postprocess_entities`, `dna_statements_json`, …), so on this export the Entities,
Themes, DNA and SNA views rendered empty.

This module is the bridge: read the child tables once, index them by `source_key`, and hand the app
the same shapes it already knows how to render. Nothing is invented — a video with no child rows has
no findings, and that is reported as such rather than as a zero.
"""
from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

CHILD_FILES = {
    "entities": "entities.csv",
    "themes": "themes.csv",
    "dna": "dna_statements.csv",
    "sna_nodes": "sna_nodes.csv",
    "sna_edges": "sna_edges.csv",
}

#: Child-table column prefix the exporter uses for the producer's nested fields.
_ITEM = "item."


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _item(row: Mapping[str, Any]) -> dict[str, Any]:
    """The `item.*` columns as a plain mapping, so callers never see the exporter's prefix."""
    return {key[len(_ITEM):]: value for key, value in row.items() if key and key.startswith(_ITEM)}


def load_children(root: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Every child table under ``root``, as flat records with the prefix removed."""
    base = Path(root)
    loaded: dict[str, list[dict[str, Any]]] = {}
    for name, filename in CHILD_FILES.items():
        rows = _read(base / filename)
        loaded[name] = [
            {**{key: value for key, value in row.items() if key and not key.startswith(_ITEM)},
             **_item(row)}
            for row in rows
        ]
    return loaded


def by_source(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group child rows by the parent `source_key` they belong to."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("source_key") or "").strip()
        if key:
            grouped.setdefault(key, []).append(dict(row))
    return grouped


def term_counts(rows: Iterable[Mapping[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    """Most frequent labels in an entity/theme child table, counted once per video.

    Duplicates inside one video are collapsed: "the same actor mentioned twice" is one video
    mentioning that actor, which is the denominator the researcher reads.
    """
    seen: dict[str, set[str]] = {}
    for row in rows:
        label = str(row.get("label") or row.get("name") or "").strip()
        key = str(row.get("source_key") or "")
        if label:
            seen.setdefault(label, set()).add(key)
    ranked = sorted(seen.items(), key=lambda item: (-len(item[1]), item[0].lower()))
    return [{"Term": label, "Videos / mentions": len(keys)} for label, keys in ranked[:limit]]


def statements(rows: Iterable[Mapping[str, Any]], limit: int = 5000) -> list[dict[str, Any]]:
    """DNA statements in the shape the app's DNA table renders."""
    out: list[dict[str, Any]] = []
    for row in rows:
        actor = str(row.get("actor_name_raw") or row.get("actor_name") or "").strip()
        concept = str(row.get("concept_label_raw") or row.get("concept") or "").strip()
        if not (actor or concept):
            continue
        out.append(
            {
                "document": str(row.get("source_key") or ""),
                "actor": actor,
                "actor_id": str(row.get("actor_id") or ""),
                "concept": concept,
                "concept_id": str(row.get("concept_id") or ""),
                "stance": str(row.get("stance") or row.get("position") or "").strip(),
                "evidence_quote": str(row.get("evidence_quote") or "").strip(),
                "confidence": str(row.get("confidence") or "").strip(),
            }
        )
        if len(out) >= limit:
            break
    return out


def network(rows_nodes: Iterable[Mapping[str, Any]], rows_edges: Iterable[Mapping[str, Any]],
            limit: int = 5000) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """SNA nodes and edges in the shape the app's network view renders."""
    nodes: list[dict[str, Any]] = []
    for row in rows_nodes:
        label = str(row.get("label") or row.get("name") or row.get("canonical_item_id") or "").strip()
        if label:
            nodes.append({"id": label, "label": label,
                          "kind": str(row.get("kind") or row.get("actor_type") or "actor")})
        if len(nodes) >= limit:
            break
    edges: list[dict[str, Any]] = []
    for row in rows_edges:
        source = str(row.get("source_actor") or row.get("source_label") or row.get("source") or "").strip()
        target = str(row.get("target_actor") or row.get("target_label") or row.get("target") or "").strip()
        if not (source and target):
            continue
        edges.append({
            "source": source,
            "target": target,
            "relation_type": str(row.get("edge_type") or row.get("relation_type") or "").strip(),
            "evidence_quote": str(row.get("evidence_quote") or "").strip(),
            "confidence": str(row.get("confidence") or "").strip(),
        })
        if len(edges) >= limit:
            break
    return nodes, edges


def coverage(children: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """How many videos each child table touches — the denominator for an empty-looking view."""
    rows = []
    for name, items in children.items():
        videos = {str(item.get("source_key") or "") for item in items if item.get("source_key")}
        rows.append({"child table": name, "rows": len(items), "videos": len(videos)})
    return rows
