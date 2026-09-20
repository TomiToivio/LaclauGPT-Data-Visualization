"""Streamlit renderer for the coordinated AI26 DNA + framing + MCA workspace."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from .multimethod_views import (
    METHOD_GUARDRAILS,
    actor_concept_edges,
    axis_contributions,
    cross_method_profile,
    discover_multimethod_artifacts,
    dna_communities,
    dna_edges,
    evidence_for_statement_ids,
    filter_statements,
    frame_flow,
    frame_matrix,
    frames_frame,
    load_multimethod_artifact,
    mca_tables,
    validate_multimethod_artifact,
    statements_frame,
    temporal_dna,
)


def _artifact_picker(roots: list[Path]) -> dict[str, Any] | None:
    paths = discover_multimethod_artifacts(*roots)
    uploaded = st.file_uploader("Open AI26 multimethod artifact", type=["json"], key="ai26-multimethod-upload")
    if uploaded is not None:
        try:
            payload = uploaded.getvalue().decode("utf-8")
            import json
            artifact = json.loads(payload)
            if not isinstance(artifact, dict):
                raise ValueError("multimethod artifact must be a JSON object")
            errors = validate_multimethod_artifact(artifact)
            if errors:
                raise ValueError("; ".join(errors))
            return artifact
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            st.error(f"Cannot open multimethod artifact: {exc}")
            return None
    if not paths:
        st.info("No laclaugpt.multimethod.v1 artifact found under configured local analysis/data directories.")
        return None
    selected = st.selectbox("Analysis artifact", paths, format_func=lambda value: value.name)
    try:
        return load_multimethod_artifact(selected)
    except (OSError, ValueError) as exc:
        st.error(f"Cannot load artifact: {exc}")
        return None


def _statement_filters(artifact: dict[str, Any]) -> pd.DataFrame:
    raw = statements_frame(artifact)
    if raw.empty:
        return raw
    cols = st.columns(4)
    arenas = sorted(raw.get("arena", pd.Series(dtype=str)).dropna().astype(str).unique())
    platforms = sorted(raw.get("platform", pd.Series(dtype=str)).dropna().astype(str).unique())
    actors = sorted(raw.get("actor_id", pd.Series(dtype=str)).dropna().astype(str).unique())
    concepts = sorted(raw.get("concept_id", pd.Series(dtype=str)).dropna().astype(str).unique())
    arena_sel = set(cols[0].multiselect("Arena", arenas))
    platform_sel = set(cols[1].multiselect("Platform", platforms))
    actor_sel = set(cols[2].multiselect("Actor / organization", actors))
    concept_sel = set(cols[3].multiselect("Concept / claim", concepts))

    cols = st.columns(4)
    statuses = sorted(raw.get("validation_status", pd.Series(dtype=str)).dropna().astype(str).unique())
    status_sel = set(cols[0].multiselect("Review status", statuses))
    min_conf = cols[1].slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
    include_abstained = cols[2].checkbox("Include abstained", value=False)
    threshold = cols[3].number_input("Network edge threshold", min_value=0.0, value=0.0, step=0.1)
    st.session_state["ai26_edge_threshold"] = float(threshold)

    timestamp = raw.get("timestamp")
    start = end = None
    if timestamp is not None and timestamp.notna().any():
        minimum = timestamp.min().date()
        maximum = timestamp.max().date()
        dates = st.date_input("Time window", value=(minimum, maximum), min_value=minimum, max_value=maximum)
        if isinstance(dates, tuple) and len(dates) == 2:
            start = pd.Timestamp(dates[0], tz="UTC")
            end = pd.Timestamp(dates[1], tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

    return filter_statements(
        artifact,
        start=start,
        end=end,
        arenas=arena_sel or None,
        platforms=platform_sel or None,
        actors=actor_sel or None,
        concepts=concept_sel or None,
        review_statuses=status_sel or None,
        min_confidence=min_conf,
        include_abstained=include_abstained,
    )


def _dna_view(artifact: dict[str, Any], selected: pd.DataFrame) -> None:
    st.markdown("### Discourse Network Analysis")
    st.caption("Communities are descriptive proposals, not ideologies. Congruence and conflict are shown separately.")
    bipartite = actor_concept_edges(selected)
    if bipartite.empty:
        st.caption("No selected actor-concept statements.")
    else:
        st.markdown("#### Actor–concept signed statements")
        st.dataframe(bipartite, use_container_width=True, hide_index=True)

    projection = st.radio(
        "DNA projection",
        ["actor_congruence", "actor_conflict", "concept_congruence", "concept_conflict"],
        horizontal=True,
    )
    edges = dna_edges(artifact, projection)
    threshold = float(st.session_state.get("ai26_edge_threshold", 0.0))
    if not edges.empty:
        weight_col = next((name for name in ("weight", "count", "score") if name in edges), None)
        if weight_col is not None and threshold > 0:
            edges = edges[pd.to_numeric(edges[weight_col], errors="coerce").fillna(0) >= threshold]
        st.dataframe(edges, use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(edges)} edges after the explicit threshold. No hidden backbone filtering is applied here.")
    else:
        st.caption("No edges in this upstream projection.")

    communities = dna_communities(artifact)
    if not communities.empty:
        st.markdown("#### Upstream community proposals")
        st.dataframe(communities, use_container_width=True, hide_index=True)

    temporal = temporal_dna(artifact)
    if not temporal.empty:
        st.markdown("#### Temporal DNA windows")
        st.dataframe(temporal, use_container_width=True, hide_index=True)
        st.caption("Stable actor/concept IDs are preserved across upstream windows. Frequency is not importance.")


def _framing_view(artifact: dict[str, Any]) -> None:
    st.markdown("### Framing")
    by = st.selectbox("Frame matrix rows", ["actor_id", "concept_id", "arena", "platform"])
    matrix = frame_matrix(artifact, by=by)
    if matrix.empty:
        st.caption("No compatible grounded frame elements in this artifact.")
    else:
        chart = matrix.reset_index().melt(id_vars=[by], var_name="frame_component", value_name="count")
        st.plotly_chart(px.density_heatmap(chart, x="frame_component", y=by, z="count", histfunc="sum"), use_container_width=True)
        st.dataframe(matrix, use_container_width=True)

    flow = frame_flow(artifact)
    if not flow.empty:
        st.markdown("#### Coded frame-structure co-occurrence")
        st.dataframe(flow, use_container_width=True, hide_index=True)
        st.caption("This ordered display summarizes coded co-occurrence. It does not claim causal flow or frame effectiveness.")

    frames = frames_frame(artifact)
    if not frames.empty:
        st.markdown("#### Grounded frame elements")
        st.dataframe(frames, use_container_width=True, hide_index=True)


def _mca_view(artifact: dict[str, Any]) -> None:
    st.markdown("### Bourdieu / MCA geometric space")
    tables = mca_tables(artifact)
    if not tables:
        st.caption("No upstream MCA payload in this artifact.")
        return
    points = tables["points"]
    provenance = tables["provenance"]
    dims = [column for column in points.columns if str(column).startswith("Dim")] if isinstance(points, pd.DataFrame) else []
    if len(dims) < 2:
        st.caption("Fewer than two MCA dimensions are available.")
        return
    axes = st.columns(2)
    x = axes[0].selectbox("Horizontal axis", dims, index=0)
    y = axes[1].selectbox("Vertical axis", dims, index=min(1, len(dims) - 1))
    clusters = tables["clusters"]
    plot = points.copy()
    if isinstance(clusters, pd.DataFrame) and not clusters.empty:
        plot = plot.merge(clusters, on="id", how="left")
    color = "cluster" if "cluster" in plot else None
    st.plotly_chart(px.scatter(plot, x=x, y=y, hover_name="id", color=color, title=f"MCA factor plane: {x} × {y}"), use_container_width=True)

    active = tables["categories"]
    supplementary = tables["supplementary"]
    if isinstance(active, pd.DataFrame) and not active.empty:
        active_display = active.copy()
        active_display["status"] = "active"
        st.markdown("#### Active modalities")
        st.dataframe(active_display, use_container_width=True, hide_index=True)
    if isinstance(supplementary, pd.DataFrame) and not supplementary.empty:
        supplementary_display = supplementary.copy()
        supplementary_display["status"] = "supplementary"
        st.markdown("#### Supplementary projections")
        st.dataframe(supplementary_display, use_container_width=True, hide_index=True)

    contributions = axis_contributions(artifact, x)
    if not contributions.empty:
        st.markdown(f"#### Modalities contributing to {x}")
        st.plotly_chart(px.bar(contributions, x=x, y="category", color="variable", orientation="h"), use_container_width=True)
    inertia = tables.get("inertia_ratio") or []
    eigenvalues = tables.get("eigenvalues") or []
    st.json({"inertia_ratio": inertia, "eigenvalues": eigenvalues, "active_variables": provenance.get("active_variables", []), "supplementary_variables": provenance.get("supplementary_variables", [])})
    st.caption("The researcher interprets each axis from contributions and quality metrics. The dashboard does not auto-name axes.")


def _cross_method_view(artifact: dict[str, Any], selected: pd.DataFrame) -> None:
    st.markdown("### Cross-method comparison")
    actors = sorted(selected.get("actor_id", pd.Series(dtype=str)).dropna().astype(str).unique())
    if not actors:
        st.caption("No actor available in the current selection.")
        return
    actor = st.selectbox("Actor / organization", actors, key="ai26-cross-actor")
    profile = cross_method_profile(artifact, actor)
    columns = st.columns(3)
    columns[0].markdown("**DNA / statements**")
    columns[0].dataframe(profile["statements"], use_container_width=True, hide_index=True)
    columns[1].markdown("**Frames**")
    columns[1].dataframe(profile["frames"], use_container_width=True, hide_index=True)
    columns[2].markdown("**MCA / community**")
    columns[2].dataframe(profile["mca_point"], use_container_width=True, hide_index=True)
    if not profile["community"].empty:
        columns[2].dataframe(profile["community"], use_container_width=True, hide_index=True)
    if not profile["mca_cluster"].empty:
        columns[2].dataframe(profile["mca_cluster"], use_container_width=True, hide_index=True)
    st.markdown("#### Evidence")
    st.dataframe(profile["evidence"], use_container_width=True, hide_index=True)
    st.caption("Optional imaginary/Laclau proposals remain visible in the ordinary record/review views; they are not collapsed into a master ideology score here.")


def render_ai26_multimethod_workspace(frame: pd.DataFrame, roots: list[Path]) -> None:
    st.markdown("## AI26 multi-method Explore")
    st.caption("Coordinated claims + framing + DNA + MCA exploration. All analytical objects are produced upstream by Data Analysis.")
    st.warning(METHOD_GUARDRAILS)
    artifact = _artifact_picker(roots)
    if artifact is None:
        return
    st.caption(f"Run: {artifact.get('analysis_run_id') or 'not recorded'} · method version: {artifact.get('method_version') or 'not recorded'}")
    selected = _statement_filters(artifact)
    tabs = st.tabs(["DNA", "Framing", "MCA / GDA", "Cross-method", "Evidence"])
    with tabs[0]:
        _dna_view(artifact, selected)
    with tabs[1]:
        _framing_view(artifact)
    with tabs[2]:
        _mca_view(artifact)
    with tabs[3]:
        _cross_method_view(artifact, selected)
    with tabs[4]:
        ids = set(selected.get("statement_id", pd.Series(dtype=str)).dropna().astype(str))
        evidence = evidence_for_statement_ids(artifact, ids)
        st.dataframe(evidence, use_container_width=True, hide_index=True)
        urls = set(evidence.get("source_url", pd.Series(dtype=str)).dropna().astype(str))
        linked = frame[frame["source_url"].astype(str).isin(urls)] if not frame.empty and "source_url" in frame else pd.DataFrame()
        st.caption(f"Canonical records linked in the current dashboard selection: {len(linked)} / {len(urls)}")
        if not linked.empty:
            columns = [column for column in ("source_url", "source_author", "summary", "review_status") if column in linked]
            st.dataframe(linked[columns], use_container_width=True, hide_index=True)
