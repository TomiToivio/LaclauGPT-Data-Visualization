import json

import pytest

from laclaugpt_visualization.multimethod_views import (
    METHOD_GUARDRAILS,
    actor_concept_edges,
    axis_contributions,
    cross_method_profile,
    deterministic_multimethod_snapshot,
    dna_edges,
    evidence_for_statement_ids,
    filter_statements,
    frame_flow,
    frame_matrix,
    load_multimethod_artifact,
    mca_tables,
    temporal_dna,
    validate_multimethod_artifact,
)


def artifact():
    return {
        "schema": "laclaugpt.multimethod.v1",
        "analysis_run_id": "synthetic-run",
        "method_version": "1",
        "statements": [
            {
                "statement_id": "s1", "source_record_id": "r1", "source_url": "https://example.invalid/1",
                "actor_id": "a", "actor_name": "Actor A", "concept_id": "c", "concept_label": "Public AI",
                "stance": "support", "timestamp": "2026-09-01T00:00:00Z", "arena": "elite", "platform": "rss",
                "confidence": 0.9, "validation_status": "accepted", "abstained": False,
                "evidence": {"quote": "public AI should be funded"},
            },
            {
                "statement_id": "s2", "source_record_id": "r2", "source_url": "https://example.invalid/2",
                "actor_id": "b", "actor_name": "Actor B", "concept_id": "c", "concept_label": "Public AI",
                "stance": "oppose", "timestamp": "2026-09-08T00:00:00Z", "arena": "grassroots", "platform": "x",
                "confidence": 0.7, "validation_status": "provisional", "abstained": False,
                "evidence": {"quote": "public AI is a bad idea"},
            },
            {
                "statement_id": "s3", "source_record_id": "r3", "source_url": "https://example.invalid/3",
                "actor_id": "c", "actor_name": "Actor C", "concept_id": "d", "concept_label": "Compute",
                "stance": "unknown", "timestamp": "2026-09-09T00:00:00Z", "arena": "elite", "platform": "rss",
                "confidence": 0.2, "validation_status": "provisional", "abstained": True,
            },
        ],
        "frames": [
            {"frame_id": "f1", "statement_id": "s1", "kind": "problem_definition", "text": "access gap"},
            {"frame_id": "f1", "statement_id": "s1", "kind": "causal_attribution", "text": "market concentration"},
            {"frame_id": "f1", "statement_id": "s1", "kind": "remedy", "text": "public compute"},
            {"frame_id": "f2", "statement_id": "s2", "kind": "problem_definition", "text": "state control"},
        ],
        "dna": {
            "actor_congruence": [{"source": "a", "target": "b", "weight": 0.25, "shared": ["c"]}],
            "actor_conflict": [{"source": "a", "target": "b", "weight": 1.0, "opposed": ["c"]}],
            "concept_congruence": [], "concept_conflict": [],
            "communities": [{"actor_id": "a", "community": 1}, {"actor_id": "b", "community": 2}],
            "temporal_windows": [
                {"start": "2026-09-01T00:00:00Z", "end": "2026-09-07T23:59:59Z", "actor_congruence": [], "actor_conflict": []},
                {"start": "2026-09-08T00:00:00Z", "end": "2026-09-14T23:59:59Z", "actor_congruence": [], "actor_conflict": [{"source": "a", "target": "b", "weight": 1.0}]},
            ],
        },
        "mca": {
            "schema": "laclaugpt.social-space.v1",
            "points": [{"id": "a", "Dim1": -0.5, "Dim2": 0.2}, {"id": "b", "Dim1": 0.6, "Dim2": -0.1}],
            "categories": [{"variable": "actor_type", "category": "researcher", "Dim1": -0.3, "Dim2": 0.1}],
            "category_contributions": [{"variable": "actor_type", "category": "researcher", "Dim1": 0.7, "Dim2": 0.1}],
            "row_cos2": [{"id": "a", "Dim1": 0.8, "Dim2": 0.2}],
            "category_cos2": [{"variable": "actor_type", "category": "researcher", "Dim1": 0.9, "Dim2": 0.1}],
            "supplementary": [{"variable": "formation", "category": "critical-ai", "n": 1, "Dim1": 0.4, "Dim2": 0.2}],
            "frequencies": [{"variable": "actor_type", "category": "researcher", "count": 2, "proportion": 1.0}],
            "eigenvalues": [0.5, 0.25], "inertia_ratio": [0.6, 0.3],
            "provenance": {"active_variables": ["actor_type"], "supplementary_variables": ["formation"], "dimension_naming": "researcher-required"},
        },
        "mca_clusters": [{"id": "a", "cluster": 1}, {"id": "b", "cluster": 2}],
    }


def test_filters_signed_actor_concept_and_abstention():
    data = artifact()
    selected = filter_statements(data, arenas={"elite"}, min_confidence=0.5)
    assert selected["statement_id"].tolist() == ["s1"]
    edges = actor_concept_edges(selected)
    assert edges.iloc[0]["stance"] == "support"
    assert edges.iloc[0]["source_url"].endswith("/1")


def test_dna_projection_temporal_and_evidence_navigation():
    data = artifact()
    assert dna_edges(data, "actor_conflict").iloc[0]["weight"] == 1.0
    temporal = temporal_dna(data)
    assert temporal.iloc[0]["projection"] == "actor_conflict"
    evidence = evidence_for_statement_ids(data, {"s2"})
    assert evidence.iloc[0]["source_url"].endswith("/2")


def test_frame_matrix_flow_and_cross_method_profile():
    data = artifact()
    matrix = frame_matrix(data, by="actor_id")
    assert matrix.loc["a", "problem_definition"] == 1
    flow = frame_flow(data)
    assert {tuple(row) for row in flow[["source", "target"]].to_records(index=False)} >= {
        ("problem_definition", "causal_attribution"),
        ("causal_attribution", "remedy"),
    }
    profile = cross_method_profile(data, "a")
    assert profile["community"].iloc[0]["community"] == 1
    assert profile["mca_cluster"].iloc[0]["cluster"] == 1
    assert profile["evidence"].iloc[0]["statement_id"] == "s1"


def test_mca_active_supplementary_contributions_and_guardrail():
    data = artifact()
    tables = mca_tables(data)
    assert tables["provenance"]["active_variables"] == ["actor_type"]
    assert tables["supplementary"].iloc[0]["variable"] == "formation"
    assert axis_contributions(data, "Dim1").iloc[0]["category"] == "researcher"
    assert "researcher interpretation" in METHOD_GUARDRAILS


def test_empty_sparse_and_invalid_schema(tmp_path):
    empty = {"schema": "laclaugpt.multimethod.v1", "statements": [], "frames": [], "dna": {}, "mca": None}
    assert filter_statements(empty).empty
    assert frame_matrix(empty).empty
    assert mca_tables(empty) == {}
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(empty), encoding="utf-8")
    assert load_multimethod_artifact(path)["schema"] == "laclaugpt.multimethod.v1"
    path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_multimethod_artifact(path)


def test_current_contract_requires_traceable_unique_statements():
    data = artifact()
    assert validate_multimethod_artifact(data) == []

    missing_source = artifact()
    missing_source["statements"][0].pop("source_url")
    assert "missing source_url" in validate_multimethod_artifact(missing_source)[0]

    duplicate = artifact()
    duplicate["statements"][1]["statement_id"] = "s1"
    assert any("duplicate statement_id: s1" in item for item in validate_multimethod_artifact(duplicate))


def test_deterministic_chart_input_snapshot_preserves_source_urls():
    data = artifact()
    expected = deterministic_multimethod_snapshot(data)

    reordered = artifact()
    reordered["statements"] = list(reversed(reordered["statements"]))
    reordered["frames"] = list(reversed(reordered["frames"]))
    assert deterministic_multimethod_snapshot(reordered) == expected

    actor_rows = expected["actor_concept"]
    assert [row["statement_id"] for row in actor_rows] == ["s1", "s2", "s3"]
    assert [row["source_url"] for row in actor_rows] == [
        "https://example.invalid/1",
        "https://example.invalid/2",
        "https://example.invalid/3",
    ]


def test_invalid_embedded_mca_contract_is_rejected(tmp_path):
    data = artifact()
    data["mca"]["schema"] = "wrong"
    errors = validate_multimethod_artifact(data)
    assert errors == ["mca must use schema laclaugpt.social-space.v1"]

    path = tmp_path / "bad-mca.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="social-space"):
        load_multimethod_artifact(path)
