"""Streamlit page for the isolated Phase 1 DNA visualization capability."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .dna_views import (
    DEFAULT_ROW_LIMIT,
    DNA_PROJECTIONS,
    actor_concept_statement_edges,
    dna_capability,
    dna_coverage,
    evidence_for_statement,
    load_dna_artifact,
    projection_edges,
)

DNA_CAVEAT = (
    "DNA views are descriptive representations of upstream Analysis output. "
    "Congruence is not ideological identity, conflict is not automatically political antagonism, "
    "frequency/weight is not importance, and network structure is not evidence of hegemony."
)


def discover_dna_artifacts(*roots: str | Path | None) -> list[Path]:
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
                    head = handle.read(1024)
                if "laclaugpt.multimethod.v1" in head and '"dna"' in head:
                    found.append(candidate)
            except OSError:
                continue
    return sorted(set(found), key=lambda item: item.stat().st_mtime, reverse=True)


def _artifact_picker(roots: list[Path]) -> dict[str, Any] | None:
    uploaded = st.file_uploader(
        "Open Analysis DNA artifact",
        type=["json"],
        key="phase1-dna-upload",
    )
    if uploaded is not None:
        try:
            artifact = json.loads(uploaded.getvalue().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            st.error(f"Cannot open DNA artifact: {exc}")
            return None
        return artifact

    paths = discover_dna_artifacts(*roots)
    if not paths:
        st.info(
            "DNA visualization is disabled: no stable upstream DNA artifact was found. "
            "Visualization will not compute DNA locally."
        )
        return None
    selected = st.selectbox("Analysis artifact", paths, format_func=lambda value: value.name)
    try:
        return load_dna_artifact(selected)
    except (OSError, ValueError) as exc:
        st.error(f"Cannot open DNA artifact: {exc}")
        return None


def render_dna_workspace(frame: pd.DataFrame, roots: list[Path]) -> None:
    st.markdown("## Discourse Network Analysis")
    st.caption("Phase 1 isolated capability. All DNA analysis is produced upstream by Data Analysis.")
    st.warning(DNA_CAVEAT)

    artifact = _artifact_picker(roots)
    if artifact is None:
        return

    capability = dna_capability(artifact)
    if not capability.available:
        st.warning(
            "DNA visualization remains disabled because the upstream contract is not stable: "
            f"{capability.reason}. No fallback analysis is performed here."
        )
        return

    st.caption(
        f"Upstream contract accepted · {capability.statement_count} statements · "
        f"{capability.projection_count} populated projections"
    )
    coverage = dna_coverage(artifact)
    if coverage:
        st.json({"coverage": dict(coverage)}, expanded=False)

    controls = st.columns(3)
    include_abstained = controls[0].checkbox("Include abstained statements", value=False)
    minimum_weight = controls[1].number_input(
        "Minimum upstream edge weight",
        min_value=0.0,
        value=0.0,
        step=0.1,
    )
    row_limit = controls[2].number_input(
        "Maximum rows per table",
        min_value=1,
        max_value=5000,
        value=DEFAULT_ROW_LIMIT,
        step=100,
    )

    st.markdown("### Actor–concept statements")
    statements = actor_concept_statement_edges(
        artifact,
        include_abstained=include_abstained,
        limit=int(row_limit),
    )
    if statements.empty:
        st.caption("No upstream actor–concept statements match this view.")
    else:
        st.dataframe(statements, use_container_width=True, hide_index=True)
        st.caption(
            "Each row preserves the Analysis statement ID and source_url. "
            "No actor/concept coding is inferred in Visualization."
        )

    st.markdown("### Upstream projection")
    projection = st.radio("Projection", list(DNA_PROJECTIONS), horizontal=True)
    edges = projection_edges(
        artifact,
        projection,
        minimum_weight=float(minimum_weight),
        limit=int(row_limit),
    )
    if edges.empty:
        st.caption("No edges in this upstream projection.")
    else:
        st.dataframe(edges, use_container_width=True, hide_index=True)
        st.caption(
            "Rows are bounded only for rendering. Edge weights and projection semantics "
            "are accepted from Analysis unchanged."
        )

    st.markdown("### Evidence traceability")
    ids = sorted(statements.get("statement_id", pd.Series(dtype=str)).dropna().astype(str).unique())
    if not ids:
        st.caption("No statement evidence is available in the current view.")
        return
    statement_id = st.selectbox("Statement", ids, key="phase1-dna-statement")
    evidence = evidence_for_statement(artifact, statement_id)
    st.dataframe(evidence, use_container_width=True, hide_index=True)
    urls = set(evidence.get("source_url", pd.Series(dtype=str)).dropna().astype(str))
    linked = (
        frame[frame["source_url"].astype(str).isin(urls)]
        if not frame.empty and "source_url" in frame
        else pd.DataFrame()
    )
    st.caption(f"Canonical source records linked by source_url: {len(linked)} / {len(urls)}")
    if not linked.empty:
        columns = [
            column
            for column in ("source_url", "source_author", "summary", "review_status")
            if column in linked
        ]
        st.dataframe(linked[columns], use_container_width=True, hide_index=True)
