"""Phase 2 Social Network Analysis workspace.

Visualization consumes an explicit Analysis-owned NETWORK product. It never derives
social ties, centrality, communities, or theoretical interpretations locally.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from typing import Any

import streamlit as st

from .graph_explorer import plotly_network_figure
from .products import DataProduct, ProductKind
from .sna import SNA_CAVEAT, filter_sna_product, sna_capability, sna_envelope


def network_product_from_mapping(data: Mapping[str, Any]) -> DataProduct:
    """Normalize a portable Analysis NETWORK artifact without changing its semantics."""
    raw_kind = str(data.get("kind") or data.get("product_kind") or "network").casefold()
    if raw_kind != ProductKind.NETWORK.value:
        raise ValueError("Phase 2 SNA requires an explicit Analysis NETWORK product.")
    payload = data.get("payload", data)
    if not isinstance(payload, Mapping):
        raise ValueError("NETWORK payload must be a JSON object.")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("NETWORK payload must contain list-valued nodes and edges.")
    metadata = data.get("metadata")
    return DataProduct(
        kind=ProductKind.NETWORK,
        payload=dict(payload),
        project=str(data.get("project") or "") or None,
        dataset=str(data.get("dataset") or "") or None,
        version=str(data.get("version") or "1"),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalized = {
            key: json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list, tuple))
            else value
            for key, value in row.items()
        }
        writer.writerow(normalized)
    return handle.getvalue().encode("utf-8")


def render_sna_workspace() -> None:
    st.markdown("### Social Network Analysis")
    st.caption(
        "Phase 2 view over ordinary upstream network structures and metrics. "
        "Metrics retain their conventional names; none is relabelled as Castells network power."
    )
    uploaded = st.file_uploader(
        "Open Analysis NETWORK artifact",
        type=["json"],
        key="phase2-sna-upload",
    )
    if uploaded is None:
        st.info(
            "No SNA artifact selected. Export a NETWORK product from Data Analysis and open it here. "
            "Visualization will not synthesize missing ties, metrics, communities, or temporal slices."
        )
        st.caption(SNA_CAVEAT)
        return
    try:
        raw = json.loads(uploaded.getvalue().decode("utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("NETWORK artifact must be a JSON object.")
        product = network_product_from_mapping(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        st.error(f"Cannot open SNA artifact: {exc}")
        return

    capability = sna_capability(product)
    if not capability.available:
        st.error(capability.reason)
        return

    payload = product.payload
    raw_nodes = [item for item in payload["nodes"] if isinstance(item, Mapping)]
    raw_edges = [item for item in payload["edges"] if isinstance(item, Mapping)]

    actor_types = sorted(
        {
            str(item.get("node_type") or item.get("type") or "actor")
            for item in raw_nodes
        }
    )
    platforms = sorted(
        {
            str(value)
            for item in [*raw_nodes, *raw_edges]
            for value in (
                item.get("platform"),
                (item.get("metadata") or {}).get("platform")
                if isinstance(item.get("metadata"), Mapping)
                else None,
            )
            if value
        }
    )
    discourse_values: set[str] = set()
    for item in [*raw_nodes, *raw_edges]:
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        for key in ("concept", "concepts", "discourse_concept", "formation", "formations"):
            value = item.get(key, metadata.get(key))
            if isinstance(value, str) and value:
                discourse_values.add(value)
            elif isinstance(value, (list, tuple, set)):
                discourse_values.update(str(entry) for entry in value if entry)

    st.markdown("#### Filters")
    first, second = st.columns(2)
    selected_types = first.multiselect("Actor / node types", actor_types, default=actor_types)
    selected_platforms = second.multiselect("Platforms", platforms)
    third, fourth = st.columns(2)
    selected_discourse = third.multiselect(
        "Discourse concept / formation",
        sorted(discourse_values),
    )
    project_filter = fourth.text_input(
        "Project",
        value=product.project or "",
        help="Matches the Analysis product project exactly; blank means any.",
    )
    fifth, sixth, seventh = st.columns(3)
    dataset_filter = fifth.text_input(
        "Dataset",
        value=product.dataset or "",
        help="Matches the Analysis product dataset exactly; blank means any.",
    )
    start_date = sixth.text_input("Start date", placeholder="YYYY-MM-DD")
    end_date = seventh.text_input("End date", placeholder="YYYY-MM-DD")

    product = filter_sna_product(
        product,
        node_types=tuple(selected_types),
        platforms=tuple(selected_platforms),
        project=project_filter.strip() or None,
        dataset=dataset_filter.strip() or None,
        start=start_date.strip() or None,
        end=end_date.strip() or None,
        discourse=tuple(selected_discourse),
    )
    payload = product.payload

    max_nodes, max_edges = st.columns(2)
    node_limit = int(max_nodes.number_input("Max nodes", 10, 2000, 250, 10))
    edge_limit = int(max_edges.number_input("Max edges", 10, 5000, 500, 10))

    graph = sna_envelope(product, max_nodes=node_limit, max_edges=edge_limit)
    metrics = st.columns(4)
    metrics[0].metric("Visible nodes", len(graph.nodes))
    metrics[1].metric("Visible edges", len(graph.edges))
    metrics[2].metric("Truncated", "yes" if graph.truncated else "no")
    metrics[3].metric("Contract", str(graph.metadata.get("contract", "unknown")))

    if graph.nodes:
        st.plotly_chart(plotly_network_figure(graph), use_container_width=True)
    else:
        st.info("No SNA nodes match the current filter.")

    st.caption(SNA_CAVEAT)
    st.markdown("#### Upstream metrics")
    measures = payload.get("measures")
    if isinstance(measures, Mapping) and measures:
        st.json(dict(measures))
    else:
        st.caption("No metrics supplied by Analysis. Visualization does not calculate them.")

    st.markdown("#### Evidence and provenance")
    evidence_rows = []
    for edge in graph.edges:
        refs = edge.get("provenance_refs") or []
        source_url = (edge.get("properties") or {}).get("source_url")
        if refs or source_url:
            evidence_rows.append(
                {
                    "edge": edge.get("id"),
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "source_url": source_url,
                    "provenance_refs": refs,
                }
            )
    if evidence_rows:
        st.dataframe(evidence_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("This artifact does not expose edge-level evidence/provenance references.")

    st.markdown("#### Exchange")
    st.caption(
        "GraphML/GEXF/RDF should normally be downloaded from the canonical Analysis export so "
        "projection and ontology semantics round-trip unchanged. The portable node/edge tables "
        "below are loss-minimizing inspection exports of the currently visible SNA subgraph."
    )
    left, right = st.columns(2)
    left.download_button(
        "Download visible nodes CSV",
        data=_csv_bytes([dict(item) for item in graph.nodes]),
        file_name="laclaugpt-phase2-sna-nodes.csv",
        mime="text/csv",
    )
    right.download_button(
        "Download visible edges CSV",
        data=_csv_bytes([dict(item) for item in graph.edges]),
        file_name="laclaugpt-phase2-sna-edges.csv",
        mime="text/csv",
    )

    upstream_exports = product.metadata.get("exports")
    if isinstance(upstream_exports, Mapping) and upstream_exports:
        st.markdown("##### Canonical Analysis exports")
        st.json(dict(upstream_exports))
