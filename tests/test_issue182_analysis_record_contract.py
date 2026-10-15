"""Regression contract: Analysis 1.2.0 records must remain lossless for researchers.

Synthetic-only fixtures. No live database, credentials or research material.
"""
import json
from pathlib import Path

import pytest

from laclaugpt_visualization.canonical import flatten_canonical
from laclaugpt_visualization.provenance import summarize_provenance

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "research-record.schema.json"


def analysis_record(version):
    return {
        "schema_version": version,
        "source_url": "https://example.invalid/ai26/synthetic-182",
        "raw_capture": {
            "ref": "fixture://raw/182", "payload": None,
            "checksum": "sha256:synthetic", "content_type": "text/plain",
            "captured_at": "2026-10-15T00:00:00Z",
        },
        "source": {"platform": "web", "country": "FI", "language": "en"},
        "content": {"text": "Entirely synthetic statement", "media_references": []},
        "intermediate": {
            "asr": [], "ocr": [], "frames": [], "frame_analysis": [],
            "translations": [], "stage_outputs": {
                "2": {"status": "not_applicable"},
                "3": {"status": "not_applicable"},
                "7": {"status": "experimental_phase_2", "ref": "fixture://dna/182"},
                "8": {"status": "experimental_phase_2", "ref": "fixture://sna/182"},
            },
        },
        "evidence": [{"id": "ev182", "ref": "fixture://evidence/182",
                      "provenance_id": "pv182"}],
        "analysis": {
            "status": "complete", "codebook_refs": [{"id": "ai26-synthetic"}],
            "model_runs": [{"model": "synthetic-model", "prompt_revision": "prompt-v3"}],
            "relations": [{"id": "rel182", "source_ref": "ev182",
                           "phase_status": "experimental_phase_2"}],
        },
        "human_readable": {
            "summary": "Synthetic only", "markdown": "Synthetic only",
            "generated_at": None, "generator": "test",
        },
        "provenance": [{
            "provenance_id": "pv182", "run_id": "run-182",
            "prompt_revision": "prompt-v3", "model": "synthetic-model",
            "codebook_version": "v2", "pipeline_version": "ai26-synthetic",
            "stage": "6",
        }],
        "review": {"status": "PROVISIONAL", "history": [{"action": "queued"}]},
        "legacy": {"historical_key": "keep-me"},
    }


@pytest.mark.parametrize("version", ["1.1.0", "1.2.0"])
def test_analysis_version_contract_and_lossless_projection(version):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    record = analysis_record(version)
    assert version in schema["properties"]["schema_version"]["enum"]
    assert set(schema["required"]).issubset(record)
    assert set(record).issubset(schema["properties"])

    # Adapter is read-only. All canonical fields must be available to record inspector.
    row = flatten_canonical(record)
    assert row["schema_version"] == version
    assert row["raw_record"]["source_url"] == record["source_url"]
    assert row["raw_record"]["intermediate"] == record["intermediate"]
    assert row["evidence"] == record["evidence"]
    assert row["provenance"] == record["provenance"]
    assert row["review"] == record["review"]
    assert row["legacy"]["historical_key"] == "keep-me"
    assert row["review_status"] == "PROVISIONAL"
    assert row["relations"][0]["phase_status"] == "experimental_phase_2"
    summary = summarize_provenance(row)
    assert summary["run_id"] == "run-182"
    assert summary["model"] == "synthetic-model"
    assert summary["codebook_version"] == "v2"


def test_unwrapped_analysis_envelope_preserves_transport_provenance():
    record = analysis_record("1.2.0")
    envelope = {
        "source_url": record["source_url"], "run_id": "run-182",
        "provenance": {"worker": "synthetic"}, "result": record,
    }
    row = flatten_canonical(envelope)
    assert row["provenance"] == record["provenance"]
    assert row["raw_record"]["transport_provenance"] == {"worker": "synthetic"}
    assert row["raw_record"]["run_id"] == "run-182"


def test_future_version_not_silently_accepted():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert "1.3.0" not in schema["properties"]["schema_version"]["enum"]


def test_ai26_mongo_routing_matches_analysis_contract():
    from laclaugpt_visualization.config import Settings
    from laclaugpt_visualization.distributed import ProjectNamespace

    # Analysis task_queue.py uses namespace.mongo_collection("analysis_results").
    expected = ProjectNamespace(project_id="ai26").mongo_collection("analysis_results")
    assert expected == "ai26__analysis_results"
    settings = Settings(project_id="ai26")
    assert settings.expected_mongodb_collection == expected
    assert settings.resolved_mongodb_collection == expected
