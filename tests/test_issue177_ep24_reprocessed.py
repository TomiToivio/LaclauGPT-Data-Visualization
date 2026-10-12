"""Synthetic, private-data-free checks for EP24 issue #177 foundation."""
import json

import pandas as pd

from laclaugpt_visualization.ep24_reprocessed import (
    STAGES, identity, multilayer, read_records, rows, status, unpack,
)


def example(country="Finland"):
    return {
        "country": country, "dataset": "EP24", "source_type": "TikTok",
        "video_id": "42", "allas_filename": "synthetic.mp4",
        "_storage_id": "row-42", "preprocess_status": "complete",
        "laclau_status": "complete",
        "dna_statements_json": json.dumps({"statements": [
            {"statement_id": "s42", "actor": "Alice", "concept": "Policy",
             "agreement": 1, "evidence_quote": "I support policy"}
        ]}),
        "sna_edges_json": json.dumps({"edges": [
            {"source_actor": "Alice", "target_actor": "Bob",
             "relation_type": "reply", "evidence_quote": "Alice replied to Bob"},
            {"source_actor": "Alice", "target_actor": "Carol",
             "relation_type": "friend"}  # unsupported relation must be excluded
        ]}),
    }


def test_stage_coverage_and_unknown_not_success():
    row = example()
    assert list(STAGES) == list(range(10))
    assert status(row, 0) == "available"
    assert status(row, 1) == "complete"
    assert status(row, 7) == "output present (status unknown)"
    assert status(row, 9) == "unavailable"
    assert status(row, 9, rdf_available=True) == "available"


def test_namespaced_identity_and_nested_json():
    assert identity(example("Finland")) != identity(example("Poland"))
    assert unpack('{"statements": []}') == {"statements": []}
    assert unpack("{broken") == "{broken"
    assert not identity({"country": "Finland"})


def test_graph_never_conflates_dna_with_empirical_sna():
    graph = multilayer([example()])
    types = {edge["type"] for edge in graph.edges}
    assert "statement_actor" in types
    assert "statement_concept" in types
    assert "empirical_sna:reply" in types
    assert "empirical_sna:friend" not in types
    assert all(edge["document"] == identity(example()) for edge in graph.edges)
    assert any(node["type"] == "dna_statement" for node in graph.nodes)


def test_bounded_graph_and_missing_data():
    graph = multilayer([example("Finland"), example("Poland")], max_records=1, max_edges=3)
    assert len(graph.edges) <= 3
    assert graph.warnings
    assert not multilayer([{"country": "Finland"}]).edges


def test_read_only_csv_and_nested_frame(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([example()]).to_csv(data / "combined.csv", index=False)
    loaded = read_records(tmp_path)
    assert len(loaded) == 1
    assert rows(loaded)[0]["country"] == "Finland"
    assert read_records(tmp_path / "nonexistent").empty


def test_rows_nested_dicts_not_dropped():
    df = pd.DataFrame([{"country": "Portugal", "json": {"nested": [1, 2]}}])
    assert rows(df)[0]["json"] == {"nested": [1, 2]}
