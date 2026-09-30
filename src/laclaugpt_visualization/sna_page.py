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


def _analysis_graph_product(data: Mapping[str, Any]) -> DataProduct | None:
    """Adapt the canonical Phase 2 Analysis AnalyticalGraph SNA layer."""
    if not data.get("schema_version") or not data.get("project_id"):
        return None
    raw_nodes = data.get("nodes")
    raw_edges = data.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return None
    sna_nodes = [
        item
        for item in raw_nodes
        if isinstance(item, Mapping) and str(item.get("layer") or "") == "sna"
    ]
    sna_edges = [
        item
        for item in raw_edges
        if isinstance(item, Mapping) and str(item.get("layer") or "") == "sna"
    ]
    if not sna_nodes and not sna_edges:
        return None
    renderable_ids = {
        str(item.get("id")) for item in sna_nodes
        if item.get("id") and not str(item.get("kind") or "").startswith("derived-")
    }
    by_id = {str(item.get("id")): item for item in sna_nodes if item.get("id")}
    nodes: list[dict[str, Any]] = []
    for item in sna_nodes:
        node_id = str(item.get("id") or "").strip()
        if not node_id or node_id not in renderable_ids:
            continue
        provenance = item.get("provenance")
        if not isinstance(provenance, Mapping):
            provenance = {}
        properties = item.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}
        source_url = str(provenance.get("source_url") or "").strip()
        evidence_ids = provenance.get("evidence_ids") or []
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        nodes.append({
            "id": node_id,
            "label": str(item.get("label") or node_id),
            "type": str(item.get("kind") or "actor"),
            "metadata": {
                **dict(properties),
                "uri": item.get("uri"),
                "assertion_kind": item.get("assertion_kind"),
                "valid_from": item.get("valid_from"),
                "valid_to": item.get("valid_to"),
                "snapshot_id": item.get("snapshot_id"),
                "provenance": dict(provenance),
                "source_urls": [source_url] if source_url else [],
                "evidence_ids": [str(value) for value in evidence_ids if value],
            },
        })
    edges: list[dict[str, Any]] = []
    derived_results: list[dict[str, Any]] = []
    for item in sna_edges:
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        kind = str(item.get("kind") or "related_to")
        provenance = item.get("provenance")
        if not isinstance(provenance, Mapping):
            provenance = {}
        properties = item.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}
        if kind == "describes" or source.startswith("derived:"):
            result_node = by_id.get(source)
            result_properties = (
                result_node.get("properties")
                if isinstance(result_node, Mapping)
                else {}
            )
            if not isinstance(result_properties, Mapping):
                result_properties = {}
            derived_results.append({
                "edge_id": item.get("id"),
                "result_id": source,
                "target_id": target,
                "metric": properties.get("metric"),
                "value": result_properties.get("value"),
                "method": provenance.get("method"),
                "snapshot_id": item.get("snapshot_id")
                or (
                    result_node.get("snapshot_id")
                    if isinstance(result_node, Mapping)
                    else None
                ),
                "valid_from": item.get("valid_from"),
                "valid_to": item.get("valid_to"),
                "source_relation_ids": properties.get("source_relation_ids") or [],
                "provenance": dict(provenance),
            })
            continue
        if source not in renderable_ids or target not in renderable_ids:
            continue
        evidence_ids = provenance.get("evidence_ids") or []
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        source_url = str(provenance.get("source_url") or "").strip()
        edges.append({
            "id": str(item.get("id") or f"{source}:{target}:{kind}"),
            "source": source,
            "target": target,
            "type": kind,
            "directed": bool(item.get("directed", True)),
            "weight": item.get("weight") if item.get("weight") is not None else 1.0,
            "platform": properties.get("platform"),
            "source_url": source_url or None,
            "evidence_ids": [str(value) for value in evidence_ids if value],
            "timestamp": item.get("valid_from"),
            "metadata": {
                **dict(properties),
                "uri": item.get("uri"),
                "assertion_kind": item.get("assertion_kind"),
                "valid_from": item.get("valid_from"),
                "valid_to": item.get("valid_to"),
                "snapshot_id": item.get("snapshot_id"),
                "provenance": dict(provenance),
            },
        })
    graph_metadata = data.get("metadata")
    if not isinstance(graph_metadata, Mapping):
        graph_metadata = {}
    metadata: dict[str, Any] = {
        "source_contract": "AnalyticalGraph",
        "analysis_graph_metadata": dict(graph_metadata),
    }
    if isinstance(graph_metadata.get("exports"), Mapping):
        metadata["exports"] = dict(graph_metadata["exports"])
    return DataProduct(
        kind=ProductKind.NETWORK,
        payload={"nodes": nodes, "edges": edges, "derived_results": derived_results},
        project=str(data.get("project_id") or "") or None,
        version=str(data.get("schema_version") or "1"),
        metadata=metadata,
    )


def network_product_from_mapping(data: Mapping[str, Any]) -> DataProduct:
    """Normalize an Analysis NETWORK artifact or canonical Phase 2 AnalyticalGraph."""
    graph_product = _analysis_graph_product(data)
    if graph_product is not None:
        return graph_product
    if data.get("schema_version") and data.get("project_id"):
        raise ValueError("Canonical AnalyticalGraph does not contain an SNA layer.")
    raw_kind = str(data.get("kind") or data.get("product_kind") or "network").casefold()
    if raw_kind != ProductKind.NETWORK.value:
        raise ValueError(
            "Phase 2 SNA requires an Analysis NETWORK product or canonical AnalyticalGraph."
        )
    payload = data.get("payload", data)
    if not isinstance(payload, Mapping):
        raise ValueError("NETWORK payload must be a JSON object.")  # noqa: TRY004
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("NETWORK payload must contain list-valued nodes and edges.")  # noqa: TRY004
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
        "Open Analysis NETWORK / AnalyticalGraph artifact",
        type=["json"],
        key="phase2-sna-upload",
    )
    if uploaded is None:
        st.info(
            "No SNA artifact selected. Export a NETWORK product or canonical AnalyticalGraph "
            "from Data Analysis and open it here. "
            "Visualization will not synthesize missing ties, metrics, communities, or temporal slices."
        )
        st.caption(SNA_CAVEAT)
        return
    try:
        raw = json.loads(uploaded.getvalue().decode("utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("NETWORK artifact must be a JSON object.")  # noqa: TRY004
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
        derived_results = payload.get("derived_results")
        if isinstance(derived_results, list) and derived_results:
            st.caption(
                "Canonical AnalyticalGraph statistical results are shown exactly as supplied "
                "by Analysis."
            )
            st.dataframe(derived_results, use_container_width=True, hide_index=True)
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
