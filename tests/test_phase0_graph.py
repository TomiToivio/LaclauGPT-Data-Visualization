from __future__ import annotations

from laclaugpt_visualization.phase0_adapter import adapt_phase0
from laclaugpt_visualization.phase0_graph import phase0_graph_projection


def _record() -> dict:
    return {
        "document_id": "phase0-doc-graph",
        "source_url": "https://example.test/graph",
        "phase0_ontology": {
            "jsonld": {
                "@graph": [
                    {
                        "@id": "https://laclaugpt.org/ontology/document/phase0-doc-graph",
                        "@type": "lg:Document",
                        "skos:prefLabel": "phase0-doc-graph",
                    },
                    {
                        "@id": "https://laclaugpt.org/ontology/nodal-point/ai",
                        "@type": "lg:NodalPoint",
                        "skos:prefLabel": "AI",
                        "lg:surfaceForm": "AI coordinates the demand chain.",
                    },
                    {
                        "@id": "https://laclaugpt.org/ontology/assertion/a1",
                        "@type": "lg:AnalysisAssertion",
                        "lg:subject": {
                            "@id": "https://laclaugpt.org/ontology/resource/people"
                        },
                        "lg:relation": {
                            "@id": "https://laclaugpt.org/ontology/articulates"
                        },
                        "lg:object": {
                            "@id": "https://laclaugpt.org/ontology/resource/control"
                        },
                        "lg:sourceDocument": {
                            "@id": "https://laclaugpt.org/ontology/document/phase0-doc-graph"
                        },
                        "lg:surfaceForm": "people demand control",
                        "lg:validated": True,
                    },
                ]
            },
            "turtle": "@prefix lg: <https://laclaugpt.org/ontology/> .",
        },
        "phase0_discourse": {
            "nodal_point_candidates": ["AI"],
            "articulations": [
                {"subject": "people", "object": "control", "evidence": "people demand control"}
            ],
        },
    }


def test_phase0_graph_is_isolated_provisional_and_traceable() -> None:
    adapted = adapt_phase0(_record())
    graph = phase0_graph_projection(adapted)

    assert graph["adapter"] == "phase0-discourse-graph-v1"
    assert graph["canonical_phase1_graph"] is False
    assert graph["graph_semantics"] == "phase0-candidate/provisional"
    assert graph["source_url"] == "https://example.test/graph"
    assert graph["bounded"] is True
    assert graph["truncated"] is False

    nodal = next(node for node in graph["nodes"] if node["label"] == "AI")
    assert nodal["kinds"] == ["nodal-point-candidate"]
    assert nodal["phase0_semantics"] == "candidate/provisional"
    assert nodal["source_url"] == "https://example.test/graph"

    edge = graph["edges"][0]
    assert edge["evidence_text"] == "people demand control"
    assert edge["source_url"] == "https://example.test/graph"
    assert edge["validated_flag_from_phase0"] is True
    assert edge["phase0_semantics"] == "candidate/provisional"


def test_phase0_graph_preserves_exporter_assertion_endpoints() -> None:
    graph = phase0_graph_projection(adapt_phase0(_record()))
    labels = {node["label"] for node in graph["nodes"]}

    assert "people" in labels
    assert "control" in labels
    assert len(graph["edges"]) == 1


def test_phase0_graph_bounds_nodes_and_edges_and_reports_truncation() -> None:
    graph = phase0_graph_projection(adapt_phase0(_record()), max_nodes=2, max_edges=1)

    assert len(graph["nodes"]) <= 2
    assert len(graph["edges"]) <= 1
    assert graph["truncated"] is True


def test_phase0_graph_malformed_or_missing_ontology_is_empty() -> None:
    graph = phase0_graph_projection(
        {
            "source_url": "https://example.test/empty",
            "phase0_ontology": {"jsonld": {"@graph": "not-a-list"}},
        }
    )

    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["bounded"] is True
    assert graph["truncated"] is False


def test_phase0_graph_does_not_infer_from_discourse_without_ontology() -> None:
    graph = phase0_graph_projection(
        {
            "source_url": "https://example.test/no-inference",
            "phase0_discourse": {
                "nodal_point_candidates": ["AI"],
                "articulations": [{"subject": "people", "object": "AI"}],
            },
        }
    )

    assert graph["nodes"] == []
    assert graph["edges"] == []
