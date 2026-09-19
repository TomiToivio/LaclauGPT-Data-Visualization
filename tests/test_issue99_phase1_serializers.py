from xml.etree import ElementTree

from laclaugpt_visualization.serializers import (
    to_cytoscape,
    to_graphml,
    to_graphology,
    to_tidy_tables,
)


def projection():
    return {
        "bounded": True,
        "truncated": False,
        "nodes": [
            {"id": "actor:a", "label": "Actor A", "kind": "actor"},
            {"id": "concept:x", "label": "Concept X", "kind": "concept"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "actor:a",
                "target": "concept:x",
                "type": "mentions",
                "weight": 2.0,
                "source_urls": ["https://example.invalid/1"],
                "evidence_refs": ["evidence:1"],
            }
        ],
    }


def test_cytoscape_keeps_evidence_and_epistemic_warning():
    value = to_cytoscape(projection())
    assert value["schema"] == "laclaugpt.cytoscape.v1"
    assert len(value["elements"]) == 3
    edge = value["elements"][-1]["data"]
    assert edge["source_urls"] == ["https://example.invalid/1"]
    assert edge["evidence_refs"] == ["evidence:1"]
    assert value["meta"]["descriptive_only"] is True
    assert "degree is not a nodal point" in value["meta"]["interpretation_warning"]


def test_graphology_is_import_friendly_and_keeps_evidence():
    value = to_graphology(projection())
    assert value["schema"] == "laclaugpt.graphology.v1"
    assert value["nodes"][0]["key"] == "actor:a"
    edge = value["edges"][0]
    assert edge["source"] == "actor:a"
    assert edge["attributes"]["evidence_refs"] == ["evidence:1"]
    assert value["attributes"]["bounded"] is True


def test_graphml_and_tidy_tables_are_portable():
    xml = to_graphml(projection())
    root = ElementTree.fromstring(xml)
    assert root.tag.endswith("graphml")
    assert "https://example.invalid/1" in xml
    nodes, edges = to_tidy_tables(projection())
    assert list(nodes["id"]) == ["actor:a", "concept:x"]
    assert edges.iloc[0]["source"] == "actor:a"
    assert edges.iloc[0]["evidence_refs"] == ["evidence:1"]
