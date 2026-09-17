from pathlib import Path

import pytest

from laclaugpt_visualization.plugins import default_registry
from laclaugpt_visualization.rdf import (
    RDFLimits,
    RDFProjectPolicy,
    RDFSubgraph,
    compact_uri,
    evidence_path,
    load_project_policy,
    preferred_label,
    theory_label,
    validate_read_only_sparql,
)
from laclaugpt_visualization.rdf_plugins import register_rdf_plugins


def test_project_policy_defaults_to_disabled_and_runtime_cannot_enable_it(tmp_path, monkeypatch):
    monkeypatch.setenv("LACLAUGPT_VIS_RDF_SERVICE_URL", "http://runtime-only.example")
    policy = load_project_policy(tmp_path, "AI26")
    assert policy == RDFProjectPolicy()
    registry = register_rdf_plugins(default_registry(), policy, provider_available=True)
    assert "rdf_graph_explorer" not in {plugin.spec.name for plugin in registry.all()}


def test_project_policy_enables_rdf_and_separately_gates_graphrag(tmp_path: Path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "AI26.yaml").write_text(
        "analysis:\n  rdf:\n    enabled: true\n    required: false\n    graphrag:\n      enabled: false\n",
        encoding="utf-8",
    )
    policy = load_project_policy(tmp_path, "AI26")
    assert policy.enabled
    assert not policy.graphrag_enabled
    registry = register_rdf_plugins(default_registry(), policy, provider_available=False)
    names = {plugin.spec.name for plugin in registry.all()}
    assert {"rdf_graph_explorer", "rdf_query", "rdf_export"} <= names
    assert "rdf_graphrag_context" not in names

    status = registry.status("rdf_graph_explorer", _empty_provider(), backend_capabilities=())
    assert not status.available
    assert status.missing_backends == frozenset({"rdf_provider"})


def test_graphrag_plugin_only_registers_when_project_enables_it():
    registry = register_rdf_plugins(
        default_registry(),
        RDFProjectPolicy(enabled=True, graphrag_enabled=True),
        provider_available=True,
    )
    assert "rdf_graphrag_context" in {plugin.spec.name for plugin in registry.all()}


def test_subgraph_payload_is_strictly_bounded():
    limits = RDFLimits(depth=2, nodes=2, edges=1)
    graph = RDFSubgraph.from_payload(
        {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b"}],
        },
        limits,
    )
    assert len(graph.nodes) == 2
    with pytest.raises(ValueError, match="unbounded"):
        RDFSubgraph.from_payload(
            {"nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "edges": []},
            limits,
        )


def test_limits_reject_unbounded_depth_nodes_edges_rows_and_timeouts():
    with pytest.raises(ValueError):
        RDFLimits(depth=5)
    with pytest.raises(ValueError):
        RDFLimits(nodes=1001)
    with pytest.raises(ValueError):
        RDFLimits(edges=2501)
    with pytest.raises(ValueError):
        RDFLimits(rows=5001)
    with pytest.raises(ValueError):
        RDFLimits(timeout_seconds=31)


def test_read_only_sparql_accepts_queries_and_rejects_update_or_federation():
    assert validate_read_only_sparql("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10")
    assert validate_read_only_sparql(
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\nDESCRIBE <urn:x>"
    )
    for query in (
        "INSERT DATA { <a> <b> <c> }",
        "DELETE WHERE { ?s ?p ?o }",
        "SELECT * WHERE { SERVICE <https://remote.example/sparql> { ?s ?p ?o } }",
    ):
        with pytest.raises(ValueError):
            validate_read_only_sparql(query)


def test_prefix_and_multilingual_label_rendering_keep_exact_uri_available():
    uri = "http://www.w3.org/2004/02/skos/core#Concept"
    assert compact_uri(uri) == "skos:Concept"
    resource = {"uri": uri, "labels": {"fi": "Käsite", "en": "Concept"}}
    assert preferred_label(resource, languages=("fi", "en")) == "Käsite"
    assert resource["uri"] == uri


def test_standard_and_laclaugpt_semantics_are_human_readable():
    assert compact_uri("http://www.w3.org/ns/prov#Entity") == "prov:Entity"
    assert compact_uri("https://schema.org/Person") == "schema:Person"
    assert theory_label({"types": ["urn:laclaugpt:NodalPoint"]}) == "Nodal point candidate"
    assert theory_label({"types": ["urn:laclaugpt:ChainOfEquivalence"]}) == "Chain of equivalence"


def test_evidence_provenance_path_reuses_existing_identifiers():
    path = evidence_path(
        {
            "uri": "urn:relation:1",
            "analytical_object_id": "relation-1",
            "evidence": {"span": "evidence-1"},
            "source_record_id": "record-1",
            "review_status": "ACCEPTED",
            "provenance": {
                "run_id": "run-1",
                "model": "gemma",
                "plugin": "laclau",
                "prompt_id": "prompt-1",
                "codebook_id": "codebook-1",
            },
        }
    )
    assert path["source_record"] == "record-1"
    assert path["analysis_run"] == "run-1"
    assert path["review_status"] == "ACCEPTED"


def test_rdf_plugins_are_vendor_neutral_and_read_only():
    registry = register_rdf_plugins(
        default_registry(), RDFProjectPolicy(enabled=True), provider_available=True
    )
    for name in ("rdf_graph_explorer", "rdf_query", "rdf_export"):
        plugin = registry.get(name)
        assert not plugin.spec.mutates_state
        assert plugin.spec.required_backends == frozenset({"rdf_provider"})
        source = (plugin.spec.source or "").lower()
        assert all(
            vendor not in source
            for vendor in (
                "fuseki",
                "graphdb",
                "stardog",
                "blazegraph",
                "virtuoso",
                "oxigraph",
                "rdflib",
            )
        )


def _empty_provider():
    from laclaugpt_visualization.products import InMemoryProvider

    return InMemoryProvider({})
