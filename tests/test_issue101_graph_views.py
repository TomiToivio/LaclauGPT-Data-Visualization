from laclaugpt_visualization.graph_api import GraphEnvelope
from laclaugpt_visualization.graph_views import compare_graphs, ego_graph, filter_graph, provenance_inspector


def graph():
    return GraphEnvelope(
        nodes=(
            {"id": "a", "type": "Record", "layer": "source", "timestamp": "2026-09-01T00:00:00Z"},
            {"id": "b", "type": "Signifier", "layer": "laclau", "timestamp": "2026-09-02T00:00:00Z"},
            {"id": "c", "type": "Actor", "layer": "dna", "timestamp": "2026-09-10T00:00:00Z"},
        ),
        edges=(
            {"id": "e1", "source": "a", "target": "b", "type": "articulates", "layer": "laclau", "provenance_refs": ["ev:1"]},
            {"id": "e2", "source": "b", "target": "c", "type": "statement", "layer": "dna"},
        ),
    )


def test_layer_type_and_time_filters():
    selected = filter_graph(graph(), layers={"source", "laclau"}, end="2026-09-05T00:00:00Z")
    assert {node["id"] for node in selected.nodes} == {"a", "b"}
    assert [edge["id"] for edge in selected.edges] == ["e1"]


def test_ego_expansion_is_bounded():
    one = ego_graph(graph(), ["a"], hops=1)
    assert {node["id"] for node in one.nodes} == {"a", "b"}
    two = ego_graph(graph(), ["a"], hops=2)
    assert {node["id"] for node in two.nodes} == {"a", "b", "c"}


def test_time_slice_compare_is_descriptive():
    left = ego_graph(graph(), ["a"], hops=1)
    right = graph()
    delta = compare_graphs(left, right)
    assert delta["nodes_added"] == ["c"]
    assert "no theoretical status" in delta["interpretation"]


def test_provenance_inspector_keeps_evidence_reference():
    info = provenance_inspector(graph().edges[0])
    assert info["evidence_refs"] == ["ev:1"]
