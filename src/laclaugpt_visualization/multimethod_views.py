"""Read-only view models for AI26 DNA, framing and MCA artifacts.

Consumes ``laclaugpt.multimethod.v1`` artifacts produced by Data Analysis.  No
network projection, framing inference, clustering or MCA fitting occurs here.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd

MULTIMETHOD_SCHEMA = "laclaugpt.multimethod.v1"
SOCIAL_SPACE_SCHEMA = "laclaugpt.social-space.v1"

METHOD_GUARDRAILS = (
    "Frequency is not importance/hegemony; graph degree is not a nodal point; "
    "a network community is not an ideology; an opposition edge is not automatically "
    "an antagonistic political frontier; MCA proximity is statistical proximity in a "
    "constructed space; MCA axes require researcher interpretation from contributions; "
    "frame frequency is not resonance/effectiveness; model coding remains provisional "
    "until reviewed."
)


def validate_multimethod_artifact(artifact: Mapping[str, Any]) -> list[str]:
    """Return contract violations without mutating or re-interpreting Analysis output."""
    errors: list[str] = []
    if artifact.get("schema") != MULTIMETHOD_SCHEMA:
        errors.append(f"expected schema {MULTIMETHOD_SCHEMA}")

    statements = artifact.get("statements")
    if statements is None:
        statements = []
    if not isinstance(statements, list):
        errors.append("statements must be a list")
        return errors

    seen_ids: set[str] = set()
    for index, row in enumerate(statements):
        if not isinstance(row, Mapping):
            errors.append(f"statements[{index}] must be an object")
            continue
        statement_id = str(row.get("statement_id") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        if not statement_id:
            errors.append(f"statements[{index}] is missing statement_id")
        elif statement_id in seen_ids:
            errors.append(f"duplicate statement_id: {statement_id}")
        else:
            seen_ids.add(statement_id)
        if not source_url:
            errors.append(f"statements[{index}] is missing source_url")

    mca = artifact.get("mca")
    if mca and (not isinstance(mca, Mapping) or mca.get("schema") != SOCIAL_SPACE_SCHEMA):
        errors.append(f"mca must use schema {SOCIAL_SPACE_SCHEMA}")
    return errors


def load_multimethod_artifact(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected {MULTIMETHOD_SCHEMA}")
    errors = validate_multimethod_artifact(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return payload


def deterministic_multimethod_snapshot(artifact: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build stable chart-input records for regression tests and reproducible rendering."""
    errors = validate_multimethod_artifact(artifact)
    if errors:
        raise ValueError("; ".join(errors))

    statements = actor_concept_edges(statements_frame(artifact))
    statement_columns = [
        "statement_id",
        "source_url",
        "actor_id",
        "concept_id",
        "stance",
        "validation_status",
    ]
    statement_records = (
        statements[statement_columns]
        .fillna("")
        .sort_values(["actor_id", "concept_id", "statement_id"], kind="stable")
        .to_dict(orient="records")
        if not statements.empty
        else []
    )

    flow = frame_flow(artifact)
    flow_records = (
        flow.sort_values(["source", "target"], kind="stable").to_dict(orient="records")
        if not flow.empty
        else []
    )

    conflict = dna_edges(artifact, "actor_conflict")
    conflict_sort = [column for column in ("source", "target") if column in conflict]
    if conflict.empty:
        conflict_records = []
    elif conflict_sort:
        conflict_records = conflict.sort_values(conflict_sort, kind="stable").to_dict(
            orient="records"
        )
    else:
        conflict_records = conflict.to_dict(orient="records")
    return {
        "actor_concept": statement_records,
        "frame_flow": flow_records,
        "actor_conflict": conflict_records,
    }


def discover_multimethod_artifacts(*roots: str | Path | None) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root is None:
            continue
        path = Path(root)
        if not path.exists():
            continue
        for candidate in path.rglob("*.json"):
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    head = handle.read(512)
                if MULTIMETHOD_SCHEMA in head:
                    found.append(candidate)
            except OSError:
                continue
    return sorted(set(found), key=lambda item: item.stat().st_mtime, reverse=True)


def statements_frame(artifact: Mapping[str, Any]) -> pd.DataFrame:
    rows = artifact.get("statements") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if "timestamp" in frame:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    return frame


def filter_statements(
    artifact: Mapping[str, Any],
    *,
    start: Any = None,
    end: Any = None,
    arenas: set[str] | None = None,
    platforms: set[str] | None = None,
    actors: set[str] | None = None,
    concepts: set[str] | None = None,
    review_statuses: set[str] | None = None,
    min_confidence: float | None = None,
    include_abstained: bool = False,
) -> pd.DataFrame:
    frame = statements_frame(artifact)
    if frame.empty:
        return frame
    mask = pd.Series(True, index=frame.index)
    if start is not None and "timestamp" in frame:
        mask &= frame["timestamp"] >= pd.Timestamp(start, tz="UTC")
    if end is not None and "timestamp" in frame:
        mask &= frame["timestamp"] <= pd.Timestamp(end, tz="UTC")
    for column, values in (
        ("arena", arenas),
        ("platform", platforms),
        ("actor_id", actors),
        ("concept_id", concepts),
        ("validation_status", review_statuses),
    ):
        if values and column in frame:
            mask &= frame[column].fillna("").astype(str).isin(values)
    if min_confidence is not None and "confidence" in frame:
        mask &= pd.to_numeric(frame["confidence"], errors="coerce").fillna(0) >= min_confidence
    if not include_abstained and "abstained" in frame:
        mask &= ~frame["abstained"].fillna(False).astype(bool)
    return frame.loc[mask].copy()


def actor_concept_edges(statements: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "actor_id", "actor_name", "concept_id", "concept_label", "stance", "statement_id",
        "source_url", "confidence", "validation_status", "evidence",
    ]
    if statements.empty:
        return pd.DataFrame(columns=columns)
    data = statements.copy()
    for column in columns:
        if column not in data:
            data[column] = None
    return data[columns]


def dna_edges(artifact: Mapping[str, Any], projection: str) -> pd.DataFrame:
    allowed = {"actor_congruence", "actor_conflict", "concept_congruence", "concept_conflict"}
    if projection not in allowed:
        raise ValueError(f"unsupported DNA projection: {projection}")
    return pd.DataFrame((artifact.get("dna") or {}).get(projection) or [])


def dna_communities(artifact: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame((artifact.get("dna") or {}).get("communities") or [])


def temporal_dna(artifact: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for window in (artifact.get("dna") or {}).get("temporal_windows") or []:
        for projection in ("actor_congruence", "actor_conflict"):
            for edge in window.get(projection) or []:
                rows.append({"start": window.get("start"), "end": window.get("end"), "projection": projection, **edge})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["start"] = pd.to_datetime(frame["start"], errors="coerce", utc=True)
        frame["end"] = pd.to_datetime(frame["end"], errors="coerce", utc=True)
    return frame


def frames_frame(artifact: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(artifact.get("frames") or [])


def frame_matrix(artifact: Mapping[str, Any], by: str = "actor_id") -> pd.DataFrame:
    frames = frames_frame(artifact)
    statements = statements_frame(artifact)
    if frames.empty or statements.empty or "statement_id" not in frames:
        return pd.DataFrame()
    meta_columns = [column for column in ("statement_id", "actor_id", "concept_id", "arena", "platform") if column in statements]
    joined = frames.merge(statements[meta_columns].drop_duplicates("statement_id"), on="statement_id", how="left")
    kind = "kind" if "kind" in joined else "frame_kind" if "frame_kind" in joined else None
    if kind is None or by not in joined:
        return pd.DataFrame()
    return pd.crosstab(joined[by], joined[kind])


def frame_flow(artifact: Mapping[str, Any]) -> pd.DataFrame:
    frames = frames_frame(artifact)
    if frames.empty:
        return pd.DataFrame(columns=["source", "target", "count", "statement_ids"])
    kind_col = "kind" if "kind" in frames else "frame_kind" if "frame_kind" in frames else None
    if kind_col is None:
        return pd.DataFrame(columns=["source", "target", "count", "statement_ids"])
    order = ["problem_definition", "problem", "diagnostic", "causal_attribution", "cause", "normative_evaluation", "evaluation", "remedy", "prognostic", "motivational"]
    rank = {name: index for index, name in enumerate(order)}
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in frames.to_dict(orient="records"):
        grouped[str(row.get("statement_id", ""))].append(str(row.get(kind_col, "")))
    edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for statement_id, kinds in grouped.items():
        unique = sorted(set(filter(None, kinds)), key=lambda value: rank.get(value, 999))
        for left, right in pairwise(unique):
            edges[(left, right)].add(statement_id)
    return pd.DataFrame([
        {"source": left, "target": right, "count": len(ids), "statement_ids": sorted(ids)}
        for (left, right), ids in sorted(edges.items())
    ])


def mca_tables(artifact: Mapping[str, Any]) -> dict[str, pd.DataFrame | list[float] | dict[str, Any]]:
    mca = artifact.get("mca") or {}
    if not mca:
        return {}
    if mca.get("schema") != SOCIAL_SPACE_SCHEMA:
        raise ValueError(f"expected {SOCIAL_SPACE_SCHEMA}")
    return {
        "points": pd.DataFrame(mca.get("points") or []),
        "categories": pd.DataFrame(mca.get("categories") or []),
        "contributions": pd.DataFrame(mca.get("category_contributions") or []),
        "row_cos2": pd.DataFrame(mca.get("row_cos2") or []),
        "category_cos2": pd.DataFrame(mca.get("category_cos2") or []),
        "supplementary": pd.DataFrame(mca.get("supplementary") or []),
        "frequencies": pd.DataFrame(mca.get("frequencies") or []),
        "eigenvalues": list(mca.get("eigenvalues") or []),
        "inertia_ratio": list(mca.get("inertia_ratio") or []),
        "provenance": dict(mca.get("provenance") or {}),
        "clusters": pd.DataFrame(artifact.get("mca_clusters") or []),
    }


def axis_contributions(artifact: Mapping[str, Any], axis: str, limit: int = 20) -> pd.DataFrame:
    tables = mca_tables(artifact)
    contributions = tables.get("contributions")
    if not isinstance(contributions, pd.DataFrame) or contributions.empty or axis not in contributions:
        return pd.DataFrame()
    return contributions.sort_values(axis, ascending=False).head(limit)


def evidence_for_statement_ids(artifact: Mapping[str, Any], statement_ids: set[str]) -> pd.DataFrame:
    statements = statements_frame(artifact)
    if statements.empty or "statement_id" not in statements:
        return pd.DataFrame()
    columns = [column for column in (
        "statement_id", "source_record_id", "source_url", "actor_id", "actor_name",
        "concept_id", "concept_label", "stance", "proposition", "evidence", "confidence",
        "validation_status", "abstained",
    ) if column in statements]
    return statements[statements["statement_id"].astype(str).isin(statement_ids)][columns]


def cross_method_profile(artifact: Mapping[str, Any], actor_id: str) -> dict[str, Any]:
    statements = statements_frame(artifact)
    selected = statements[statements.get("actor_id", pd.Series(dtype=str)).astype(str) == str(actor_id)] if not statements.empty else statements
    statement_ids = set(selected.get("statement_id", pd.Series(dtype=str)).astype(str))
    frames = frames_frame(artifact)
    selected_frames = frames[frames.get("statement_id", pd.Series(dtype=str)).astype(str).isin(statement_ids)] if not frames.empty else frames
    communities = dna_communities(artifact)
    community = communities[communities.get("actor_id", communities.get("id", pd.Series(dtype=str))).astype(str) == str(actor_id)] if not communities.empty else communities
    mca = mca_tables(artifact)
    points = mca.get("points") if mca else pd.DataFrame()
    point = points[points["id"].astype(str) == str(actor_id)] if isinstance(points, pd.DataFrame) and not points.empty and "id" in points else pd.DataFrame()
    clusters = mca.get("clusters") if mca else pd.DataFrame()
    cluster = clusters[clusters["id"].astype(str) == str(actor_id)] if isinstance(clusters, pd.DataFrame) and not clusters.empty and "id" in clusters else pd.DataFrame()
    return {
        "statements": selected,
        "frames": selected_frames,
        "community": community,
        "mca_point": point,
        "mca_cluster": cluster,
        "evidence": evidence_for_statement_ids(artifact, statement_ids),
    }


def concept_counts(statements: pd.DataFrame) -> pd.DataFrame:
    if statements.empty or "concept_id" not in statements:
        return pd.DataFrame(columns=["concept_id", "count"])
    counts = Counter(statements["concept_id"].fillna("").astype(str))
    return pd.DataFrame([{"concept_id": key, "count": value} for key, value in counts.items() if key]).sort_values("count", ascending=False)
