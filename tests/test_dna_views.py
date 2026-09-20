import json
from pathlib import Path

from laclaugpt_visualization.dna_views import (
    MAX_ROW_LIMIT,
    actor_concept_statement_edges,
    dna_capability,
    evidence_for_statement,
    projection_edges,
)


FIXTURE = Path(__file__).parent / "fixtures" / "dna_multimethod_v1.json"


def _artifact():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_dna_contract_is_available_and_preserves_evidence_identity():
    artifact = _artifact()
    capability = dna_capability(artifact)
    assert capability.available is True
    edges = actor_concept_statement_edges(artifact)
    assert set(edges["statement_id"]) == {"s1", "s2"}
    assert set(edges["source_url"]) == {
        "https://example.org/source/1",
        "https://example.org/source/2",
    }
    evidence = evidence_for_statement(artifact, "s1")
    assert evidence.iloc[0]["source_url"] == "https://example.org/source/1"
    assert evidence.iloc[0]["actor_id"] == "actor-a"
    assert evidence.iloc[0]["concept_id"] == "concept-x"


def test_missing_dna_output_disables_capability_without_fallback_computation():
    artifact = _artifact()
    artifact.pop("dna")
    capability = dna_capability(artifact)
    assert capability.available is False
    assert "DNA output is missing" in capability.reason


def test_missing_source_url_disables_untraceable_contract():
    artifact = _artifact()
    artifact["statements"][0].pop("source_url")
    capability = dna_capability(artifact)
    assert capability.available is False
    assert "evidence identity" in capability.reason


def test_projection_edges_are_upstream_only_and_bounded():
    artifact = _artifact()
    edges = projection_edges(artifact, "actor_congruence", minimum_weight=0.5)
    assert edges.to_dict(orient="records") == [
        {"source": "actor-a", "target": "actor-b", "weight": 1.0}
    ]
    many = dict(artifact)
    many["dna"] = dict(artifact["dna"])
    many["dna"]["actor_congruence"] = [
        {"source": f"a-{i}", "target": f"b-{i}", "weight": 1.0}
        for i in range(MAX_ROW_LIMIT + 10)
    ]
    assert len(projection_edges(many, "actor_congruence", limit=MAX_ROW_LIMIT + 10)) == MAX_ROW_LIMIT
