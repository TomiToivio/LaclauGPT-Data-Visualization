from laclaugpt_visualization.graph_api import (
    ArangoGraphBackend,
    GraphQuery,
    LocalGraphBackend,
    MongoGraphBackend,
    evidence_refs,
    jsonld_subgraph,
    layer_enabled,
)


FIXTURE = {
    "nodes": [
        {"id": "record:1", "label": "Source", "type": "Record", "provenance_refs": ["source:1"]},
        {"id": "signifier:ai", "label": "AI", "type": "Signifier"},
    ],
    "edges": [
        {
            "id": "edge:1",
            "source": "record:1",
            "target": "signifier:ai",
            "type": "articulates_signifier",
            "provenance_refs": ["evidence:1"],
        }
    ],
    "provenance": {"analysis_run": "synthetic-run"},
}


class LocalLoader:
    def __call__(self, query):
        assert query.max_nodes <= 1000
        return FIXTURE

    def describe(self, resource_id):
        return {"id": resource_id}


class MongoProvider:
    def graph_payload(self, query):
        return FIXTURE

    def describe(self, resource_id):
        return {"id": resource_id}


class ArangoProvider:
    def traverse(self, query):
        return FIXTURE

    def describe(self, resource_id):
        return {"id": resource_id}


def canonical(graph):
    payload = graph.as_dict()
    payload["metadata"].pop("backend", None)
    return payload


def test_local_mongo_arango_return_same_graph_contract():
    query = GraphQuery(layers=("source", "laclau"), max_nodes=50, max_edges=50)
    backends = (
        LocalGraphBackend(LocalLoader()),
        MongoGraphBackend(MongoProvider()),
        ArangoGraphBackend(ArangoProvider()),
    )
    graphs = [backend.graph(query) for backend in backends]
    assert all(graph.metadata["contract"] == "laclaugpt.graph.v1" for graph in graphs)
    assert canonical(graphs[0]) == canonical(graphs[1]) == canonical(graphs[2])


def test_phase_layers_use_explicit_minimum_phase_gates():
    assert layer_enabled("source", phase=0)
    assert layer_enabled("provenance", phase=0)
    assert layer_enabled("laclau", phase=0)
    assert not layer_enabled("sna", phase=0)
    assert layer_enabled("sna", phase=1)
    assert not layer_enabled("dna", phase=1)
    assert layer_enabled("dna", phase=2)
    assert layer_enabled("sna", phase=2)
    assert not layer_enabled("unknown", phase=99)


def test_graph_is_bounded_and_progressive():
    query = GraphQuery(depth=99, max_nodes=99999, max_edges=99999)
    bounded = query.bounded()
    assert bounded.depth == 4
    assert bounded.max_nodes == 1000
    assert bounded.max_edges == 2500


def test_provenance_and_jsonld_export_preserve_evidence_links():
    graph = LocalGraphBackend(LocalLoader()).graph(GraphQuery())
    assert evidence_refs(graph.edges[0]) == ("evidence:1",)
    exported = jsonld_subgraph(graph)
    source = next(item for item in exported["@graph"] if item["@id"] == "record:1")
    assert source["articulates_signifier"] == [{"@id": "signifier:ai"}]
