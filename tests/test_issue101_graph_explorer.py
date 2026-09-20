from laclaugpt_visualization.graph_api import GraphEnvelope
from laclaugpt_visualization.graph_explorer import (
    evidence_for_edge,
    filter_explorer_graph,
    jsonld_bytes,
    plotly_network_figure,
)


def _graph():
    return GraphEnvelope(
        nodes=(
            {"id": "urn:x:a", "label": "A", "type": "signifier", "layer": "laclau", "properties": {"degree": 2}},
            {"id": "urn:x:b", "label": "B", "type": "actor", "layer": "source", "properties": {"degree": 1}},
        ),
        edges=(
            {
                "id": "e1", "source": "urn:x:a", "target": "urn:x:b", "type": "articulates",
                "layer": "laclau", "weight": 2.0,
                "properties": {"source_urls": ["https://example.test/1"], "record_count": 1},
                "provenance_refs": ["span-1"],
            },
        ),
    )


def test_filter_keeps_endpoint_consistency():
    graph = filter_explorer_graph(_graph(), layers=["laclau"])
    assert [node["id"] for node in graph.nodes] == ["urn:x:a"]
    assert graph.edges == ()


def test_evidence_inspector_preserves_source_path():
    value = evidence_for_edge(_graph().edges[0])
    assert value["source_urls"] == ["https://example.test/1"]
    assert value["evidence_refs"] == ["span-1"]


def test_jsonld_export_and_plot_are_bounded_view_outputs():
    graph = _graph()
    assert b'"@graph"' in jsonld_bytes(graph)
    figure = plotly_network_figure(graph)
    assert len(figure.data) == 2
