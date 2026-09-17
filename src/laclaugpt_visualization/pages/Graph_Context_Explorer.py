"""Streamlit Graph + Context Explorer backed by the storage-neutral query contract."""
from __future__ import annotations

import json
import math
import time
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.query_backends import (
    BackendUnavailable,
    ContextRequest,
    GraphRequest,
    resolve_query_backend,
)
from laclaugpt_visualization.storage import load_local_frame


st.set_page_config(page_title="LaclauGPT Graph + Context Explorer", layout="wide")
st.title("Graph + Context Explorer")
st.caption(
    "Bounded graph browsing and optional vector context over the same research-query contract. "
    "MongoDB is preferred when configured; CSV/local remains a complete fallback."
)

settings = get_settings()
settings.ensure_local_directories()
local_frame = load_local_frame(settings)

try:
    backend = resolve_query_backend(settings, local_frame)
except BackendUnavailable as exc:
    st.error(str(exc))
    st.stop()

st.sidebar.caption(f"Research backend: {backend.name}")
st.sidebar.caption(f"Project: {settings.project_id}")

# A bounded catalog supplies filter controls and record drill-down labels. It is not a graph query.
catalog_product = backend.records(limit=min(settings.graph_max_nodes * 10, 5000))
catalog = catalog_product.payload
if not isinstance(catalog, pd.DataFrame):
    catalog = pd.DataFrame(catalog)


def _scalar_values(column: str) -> list[str]:
    if column not in catalog:
        return []
    return sorted(
        {
            str(value)
            for value in catalog[column]
            if value is not None and str(value).strip() and str(value) != "nan"
        }
    )


def _list_values(column: str) -> list[str]:
    if column not in catalog:
        return []
    values: set[str] = set()
    for items in catalog[column]:
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                value = item.get("label") or item.get("name") or item.get("id")
            else:
                value = item
            if value not in (None, ""):
                values.add(str(value))
    return sorted(values)


def _optional_select(label: str, values: list[str]) -> str | None:
    selected = st.selectbox(label, [""] + values, format_func=lambda value: value or "All")
    return selected or None


st.markdown("### Graph Explorer")
filter_columns = st.columns(4)
with filter_columns[0]:
    dataset = _optional_select("Dataset", _scalar_values("dataset"))
    country = _optional_select("Country", _scalar_values("source_country"))
with filter_columns[1]:
    arena = _optional_select("Arena", _scalar_values("arena"))
    platform = _optional_select("Platform", _scalar_values("source_platform"))
with filter_columns[2]:
    actor = _optional_select("Actor / author", _scalar_values("source_author"))
    signifier = _optional_select("Signifier", _list_values("signifiers"))
with filter_columns[3]:
    frame_filter = _optional_select("Frame", _list_values("frames"))
    depth = st.number_input(
        "Hop depth",
        min_value=1,
        max_value=settings.graph_max_depth,
        value=min(1, settings.graph_max_depth),
    )

limit_columns = st.columns(2)
with limit_columns[0]:
    node_limit = st.slider(
        "Node limit",
        min_value=10,
        max_value=max(10, settings.graph_max_nodes),
        value=min(250, settings.graph_max_nodes),
    )
with limit_columns[1]:
    edge_limit = st.slider(
        "Edge limit",
        min_value=10,
        max_value=max(10, settings.graph_max_edges),
        value=min(500, settings.graph_max_edges),
    )

request = GraphRequest(
    dataset=dataset,
    country=country,
    arena=arena,
    platform=platform,
    actor=actor,
    signifier=signifier,
    frame=frame_filter,
    depth=int(depth),
    max_nodes=int(node_limit),
    max_edges=int(edge_limit),
)

try:
    graph_product = backend.graph(request)
except BackendUnavailable as exc:
    st.warning(str(exc))
    graph_product = None


def _graph_figure(payload: dict[str, Any]) -> go.Figure:
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    count = max(1, len(nodes))
    positions = {
        str(node.get("id")): (
            math.cos((2 * math.pi * index) / count),
            math.sin((2 * math.pi * index) / count),
        )
        for index, node in enumerate(nodes)
    }
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in edges:
        source = positions.get(str(edge.get("source")))
        target = positions.get(str(edge.get("target")))
        if source is None or target is None:
            continue
        edge_x.extend([source[0], target[0], None])
        edge_y.extend([source[1], target[1], None])
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            hoverinfo="skip",
            name="relations",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[positions[str(node.get("id"))][0] for node in nodes],
            y=[positions[str(node.get("id"))][1] for node in nodes],
            mode="markers",
            text=[
                f"{node.get('type', '')}: {node.get('label', node.get('id', ''))}"
                for node in nodes
            ],
            customdata=[str(node.get("id", "")) for node in nodes],
            hovertemplate="%{text}<extra></extra>",
            name="nodes",
        )
    )
    figure.update_layout(
        showlegend=False,
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=650,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        dragmode="pan",
    )
    return figure


if graph_product is None:
    st.info("Graph data is unavailable for the current backend/request.")
else:
    graph = graph_product.payload
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    metric_columns = st.columns(4)
    metric_columns[0].metric("Nodes", len(nodes))
    metric_columns[1].metric("Edges", len(edges))
    metric_columns[2].metric("Backend", graph_product.metadata.get("backend", backend.name))
    metric_columns[3].metric("Bounded", "yes" if graph.get("bounded") else "no")
    if graph.get("truncated"):
        st.info("This subgraph reached a configured safety limit. Narrow the filters to inspect more detail.")
    if nodes:
        st.plotly_chart(_graph_figure(graph), use_container_width=True, config={"scrollZoom": True})
        node_ids = [str(node.get("id")) for node in nodes]
        selected_node = st.selectbox("Inspect node", node_ids)
        selected = next(node for node in nodes if str(node.get("id")) == selected_node)
        st.json(selected)
        connected = [
            edge
            for edge in edges
            if str(edge.get("source")) == selected_node or str(edge.get("target")) == selected_node
        ]
        if connected:
            st.markdown("#### Connected relations and provenance")
            st.dataframe(connected, use_container_width=True, hide_index=True)
            source_urls = sorted(
                {str(edge.get("source_url")) for edge in connected if edge.get("source_url")}
            )
            if source_urls and "source_url" in catalog:
                evidence_rows = catalog[catalog["source_url"].isin(source_urls)]
                visible = [
                    column
                    for column in ("source_url", "summary", "source_author", "source_platform", "review_status")
                    if column in evidence_rows
                ]
                if visible:
                    st.markdown("#### Supporting source records")
                    st.dataframe(evidence_rows[visible], use_container_width=True, hide_index=True)
    else:
        st.info("No graph nodes match the current filters.")

    st.download_button(
        "Export bounded subgraph JSON",
        data=json.dumps(graph, default=str, indent=2),
        file_name=f"{settings.project_id}-bounded-subgraph.json",
        mime="application/json",
    )

st.caption(
    "Graph topology is descriptive. It does not by itself establish hegemony, nodal status, "
    "empty/floating signification, antagonism, or other discourse-theoretical claims."
)

st.divider()
st.markdown("### Context Explorer / vector diagnostics")
capability = backend.vector_capability()
st.json(
    {
        "backend": capability.backend,
        "available": capability.available,
        "index_name": capability.index_name,
        "embedding_path": capability.embedding_path,
        "reason": capability.reason,
    }
)

source_urls = _scalar_values("source_url")
if not source_urls:
    st.info("No source records are available for context exploration.")
elif not capability.available:
    st.info(
        capability.reason
        or "Vector retrieval is unavailable. Ordinary record and graph views remain fully usable."
    )
else:
    selected_source = st.selectbox("Selected source record", source_urls)
    result_limit = st.slider(
        "Similar-record limit",
        min_value=1,
        max_value=min(50, settings.vector_max_results),
        value=min(10, settings.vector_max_results),
    )
    started = time.perf_counter()
    try:
        context_product = backend.context(ContextRequest(selected_source, limit=int(result_limit)))
    except BackendUnavailable as exc:
        st.warning(str(exc))
        context_product = None
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    if context_product is not None:
        diagnostics = dict(context_product.metadata)
        diagnostics["retrieval_ms"] = elapsed_ms
        diagnostics["retrieved_source_ids"] = [
            row.get("source_url") for row in context_product.payload if row.get("source_url")
        ]
        st.markdown("#### Retrieval diagnostics")
        st.json(diagnostics)
        if context_product.payload:
            st.markdown("#### Similar / neighbouring records")
            st.dataframe(context_product.payload, use_container_width=True, hide_index=True)
            neighbour_urls = tuple(
                str(row.get("source_url"))
                for row in context_product.payload
                if row.get("source_url")
            )
            if neighbour_urls:
                st.markdown("#### Hybrid vector + graph neighbourhood")
                hybrid = backend.graph(
                    GraphRequest(
                        roots=(selected_source,) + neighbour_urls,
                        depth=1,
                        max_nodes=min(settings.graph_max_nodes, 150),
                        max_edges=min(settings.graph_max_edges, 300),
                    )
                )
                st.caption(
                    f"{len(hybrid.payload.get('nodes', []))} nodes · "
                    f"{len(hybrid.payload.get('edges', []))} edges"
                )
                if hybrid.payload.get("nodes"):
                    st.plotly_chart(
                        _graph_figure(hybrid.payload),
                        use_container_width=True,
                        config={"scrollZoom": True},
                    )
        else:
            st.info(context_product.metadata.get("reason") or "No vector neighbours were returned.")

st.caption(
    "This page retrieves evidence; it does not answer research questions autonomously. "
    "RAG chat/agent plugins can consume the returned source IDs through the shared service boundary."
)
