"""Optional RDF/Linked Data researcher page for Streamlit multipage navigation."""
from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.rdf import (
    RDFLimits,
    THEORY_CAVEAT,
    compact_uri,
    configured_provider,
    evidence_path,
    load_project_policy,
    preferred_label,
    theory_label,
    validate_read_only_sparql,
)

st.set_page_config(page_title="LaclauGPT RDF Explorer", layout="wide")
st.title("RDF knowledge-graph explorer")
settings = get_settings()
policy = load_project_policy(settings.data_dir, settings.project_id)

if not policy.enabled:
    st.info(
        "RDF is disabled by project policy. Set analysis.rdf.enabled=true in the project "
        "configuration to expose RDF browsing and export. Runtime endpoint settings alone "
        "cannot enable this page."
    )
    st.stop()

provider = configured_provider(settings.project_id)
if provider is None:
    st.warning(
        "RDF is enabled for this project, but no Analysis-owned RDF service is configured. "
        "The normal CSV/MongoDB dashboard remains fully usable. Configure the private runtime "
        "variable LACLAUGPT_VIS_RDF_SERVICE_URL when an RDF provider/export service is available."
    )
    st.stop()

try:
    health = provider.health()
    capabilities = provider.capabilities()
except ConnectionError as exc:
    st.warning(str(exc))
    st.caption("RDF failure is isolated from the canonical dashboard and its normal graph views.")
    st.stop()

st.caption(THEORY_CAVEAT)
status_cols = st.columns(3)
status_cols[0].metric("RDF service", str(health.get("status", "available")))
status_cols[1].metric("Project", settings.project_id)
status_cols[2].metric("GraphRAG", "enabled" if policy.graphrag_enabled else "disabled")


def _clean(value: str) -> str | None:
    value = value.strip()
    return value or None


def _resource_uri(node: Mapping[str, Any]) -> str:
    return str(node.get("uri") or node.get("id") or "")


def _render_graph(nodes, edges) -> None:
    if not nodes:
        st.info("No RDF nodes matched the current bounded query.")
        return
    positions: dict[str, tuple[float, float]] = {}
    count = len(nodes)
    for index, node in enumerate(nodes):
        uri = _resource_uri(node)
        angle = (2 * math.pi * index) / max(count, 1)
        positions[uri] = (math.cos(angle), math.sin(angle))

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in edges:
        source = str(edge.get("source") or edge.get("subject") or "")
        target = str(edge.get("target") or edge.get("object") or "")
        if source not in positions or target not in positions:
            continue
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        edge_x.extend((x0, x1, None))
        edge_y.extend((y0, y1, None))

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        hoverinfo="none",
        line={"width": 1},
    )
    node_x, node_y, labels, hover = [], [], [], []
    for node in nodes:
        uri = _resource_uri(node)
        x, y = positions[uri]
        node_x.append(x)
        node_y.append(y)
        labels.append(preferred_label(node))
        kind = theory_label(node)
        hover.append(
            "<br>".join(
                item
                for item in (
                    preferred_label(node),
                    kind or "",
                    compact_uri(uri),
                    uri,
                )
                if item
            )
        )
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hovertext=hover,
        hoverinfo="text",
        marker={"size": 14},
    )
    figure = go.Figure(data=[edge_trace, node_trace])
    figure.update_layout(
        showlegend=False,
        xaxis={"visible": False},
        yaxis={"visible": False},
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        height=650,
    )
    st.plotly_chart(figure, use_container_width=True)


def _node_table(nodes) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "label": preferred_label(node),
                "semantic_type": theory_label(node) or "",
                "compact_uri": compact_uri(_resource_uri(node)),
                "uri": _resource_uri(node),
                "review_status": node.get("review_status"),
                "confidence": node.get("confidence"),
            }
            for node in nodes
        ]
    )


def _edge_table(edges) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": compact_uri(str(edge.get("source") or edge.get("subject") or "")),
                "predicate": compact_uri(str(edge.get("predicate") or edge.get("type") or "")),
                "target": compact_uri(str(edge.get("target") or edge.get("object") or "")),
                "confidence": edge.get("confidence"),
                "review_status": edge.get("review_status"),
            }
            for edge in edges
        ]
    )


graph_tab, query_tab, export_tab, provenance_tab = st.tabs(
    ["Graph explorer", "Query", "RDF export", "Evidence & provenance"]
)

with graph_tab:
    st.markdown("#### Bounded semantic subgraph")
    graph_options = provider.list_named_graphs()
    graph_labels = [""] + [
        str(item.get("uri") or item.get("id") or item) if isinstance(item, Mapping) else str(item)
        for item in graph_options
    ]
    c1, c2, c3 = st.columns(3)
    named_graph = c1.selectbox("Named graph / project graph", graph_labels)
    class_filter = c2.text_input("Class/type")
    predicate_filter = c3.text_input("Predicate/edge")

    c1, c2, c3 = st.columns(3)
    source_filter = c1.text_input("Source / source record")
    author_filter = c2.text_input("Author")
    formation_filter = c3.text_input("Formation")

    c1, c2, c3 = st.columns(3)
    signifier_filter = c1.text_input("Signifier")
    entity_filter = c2.text_input("Entity")
    review_filter = c3.text_input("Review state")

    c1, c2, c3 = st.columns(3)
    time_filter = c1.text_input("Time/window")
    min_confidence = c2.number_input(
        "Minimum confidence", min_value=0.0, max_value=1.0, value=0.0, step=0.05
    )
    resource_search = c3.text_input("Resource URI / search")

    c1, c2, c3 = st.columns(3)
    depth = c1.slider("Neighbor depth", min_value=0, max_value=4, value=1)
    node_limit = c2.slider("Node limit", min_value=10, max_value=1000, value=200, step=10)
    edge_limit = c3.slider("Edge limit", min_value=10, max_value=2500, value=400, step=10)
    limits = RDFLimits(depth=depth, nodes=node_limit, edges=edge_limit)
    filters = {
        key: value
        for key, value in {
            "named_graph": _clean(named_graph),
            "class": _clean(class_filter),
            "predicate": _clean(predicate_filter),
            "source": _clean(source_filter),
            "author": _clean(author_filter),
            "formation": _clean(formation_filter),
            "signifier": _clean(signifier_filter),
            "entity": _clean(entity_filter),
            "review_state": _clean(review_filter),
            "time": _clean(time_filter),
            "min_confidence": min_confidence if min_confidence > 0 else None,
            "resource": _clean(resource_search),
        }.items()
        if value is not None
    }

    if st.button("Query bounded RDF subgraph", type="primary"):
        try:
            st.session_state["rdf_subgraph"] = provider.query_subgraph(filters, limits)
        except (ConnectionError, ValueError) as exc:
            st.error(str(exc))

    graph = st.session_state.get("rdf_subgraph")
    if graph is not None:
        st.caption(
            f"{len(graph.nodes)} nodes · {len(graph.edges)} edges"
            + (" · provider truncated result" if graph.truncated else "")
        )
        view = st.radio("View", ["Graph", "Table"], horizontal=True)
        if view == "Graph":
            _render_graph(graph.nodes, graph.edges)
        else:
            st.markdown("##### Nodes")
            st.dataframe(_node_table(graph.nodes), use_container_width=True, hide_index=True)
            st.markdown("##### Edges")
            st.dataframe(_edge_table(graph.edges), use_container_width=True, hide_index=True)
        if graph.query:
            with st.expander("Query behind result"):
                st.code(graph.query, language="sparql")
        if graph.provenance:
            with st.expander("Result provenance"):
                st.json(graph.provenance)

with query_tab:
    st.markdown("#### Safe read-only semantic query")
    st.caption("The dashboard refuses SPARQL update and federation operations and applies limits/timeouts.")
    predefined = capabilities.get("predefined_queries") or []
    selected = st.selectbox("Predefined query", [""] + [str(item) for item in predefined])
    advanced = st.checkbox("Advanced read-only SPARQL editor")
    default_query = (
        "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 100"
        if advanced
        else (selected or "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 100")
    )
    sparql = st.text_area("SPARQL", value=default_query, height=220, disabled=not advanced and bool(selected))
    c1, c2 = st.columns(2)
    row_limit = c1.number_input("Result limit", 1, 5000, 500)
    timeout = c2.number_input("Timeout seconds", 1, 30, 10)
    if st.button("Run read-only query"):
        try:
            validate_read_only_sparql(sparql)
            rows = provider.query_table(sparql, limit=int(row_limit), timeout_seconds=int(timeout))
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except (ConnectionError, ValueError) as exc:
            st.error(str(exc))

with export_tab:
    st.markdown("#### Analysis-owned RDF export")
    st.caption(
        "The dashboard requests materialization from the Analysis service; it does not rebuild RDF locally."
    )
    export_format = st.selectbox(
        "Format", ["json-ld", "turtle", "n-quads", "n-triples", "trig", "rdf-xml"]
    )
    selection = st.text_area(
        "Bounded selection (JSON)",
        value='{"scope": "current_project"}',
        help="Use a bounded scope supported by the Analysis RDF service.",
    )
    if st.button("Request RDF export"):
        try:
            import json

            payload = json.loads(selection)
            receipt = provider.export(format=export_format, selection=payload, limits=RDFLimits())
            st.json(receipt)
        except (ConnectionError, ValueError, TypeError) as exc:
            st.error(str(exc))

with provenance_tab:
    st.markdown("#### Resource → evidence → source → analysis provenance")
    uri = st.text_input("Resource URI to inspect")
    if st.button("Describe resource") and uri.strip():
        try:
            resource = provider.describe_resource(uri.strip())
            st.markdown(f"##### {preferred_label(resource)}")
            st.caption(compact_uri(uri.strip()))
            if theory_label(resource):
                st.info(theory_label(resource))
            st.json(resource)
            st.markdown("##### Evidence/provenance path")
            st.json(evidence_path(resource))
        except ConnectionError as exc:
            st.error(str(exc))

    if policy.graphrag_enabled:
        st.markdown("#### RDF GraphRAG context inspector")
        st.caption("Shows selected graph paths/nodes and source evidence; it does not replace other retrieval providers.")
        context_seed = st.text_input("GraphRAG selection / resource")
        if st.button("Inspect GraphRAG context") and context_seed.strip():
            try:
                st.json(provider.graphrag_context({"resource": context_seed.strip()}))
            except ConnectionError as exc:
                st.error(str(exc))
    else:
        st.caption("RDF GraphRAG is disabled by project policy; ordinary RDF browsing/export remains available.")
