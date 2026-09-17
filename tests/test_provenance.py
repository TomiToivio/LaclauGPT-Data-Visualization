from __future__ import annotations

import json
import sqlite3

import pandas as pd

from laclaugpt_visualization.data import load_frame
from laclaugpt_visualization.provenance import (
    UNKNOWN,
    comparison_warning,
    mixed_provenance_dimensions,
    provenance_frame,
    safe_provenance_events,
    summarize_provenance,
)


def _record(run_id: str = "run-1", codebook_hash: str = "cb-aaa", rag: bool = True) -> dict:
    return {
        "schema_version": "1.0.0",
        "source_url": f"synthetic://{run_id}",
        "source": {
            "platform": "synthetic",
            "source_type": "post",
            "country": "FI",
            "language": "fi",
        },
        "content": {"text": "Synthetic provenance test"},
        "analysis": {
            "status": "complete",
            "codebook_refs": ["ai26-core"],
            "memory_refs": ["synthetic://context/legacy-memory-ref"],
            "model_runs": [
                {
                    "provider": "ollama",
                    "model": "gemma4",
                    "task_profile": "discourse-balanced",
                }
            ],
        },
        "provenance": [
            {
                "stage": "analysis",
                "run_id": run_id,
                "study_id": "AI26",
                "arena": "elite",
                "dataset": "ai26-live",
                "effective_config_version": "7",
                "effective_config_hash": "cfg-123",
                "execution_profile": "roihu",
                "context_profile": "balanced",
                "codebook_id": "ai26-core",
                "codebook_version": "2026.09",
                "codebook_hash": codebook_hash,
                "rag_enabled": rag,
                "context_memory_enabled": True,
                "embedding_model": "fixture-embed",
                "index_version": "index-3",
                "retrieval_id": "retrieval-9",
                "context_source_refs": [
                    "synthetic://context/1",
                    {"source_url": "synthetic://context/2", "private_text": "do not show"},
                ],
                "previous_summary_id": "daily-2026-09-16",
                "pipeline_version": "analysis-2.1",
                "collection_config_id": "collect-cfg-4",
                "password": "never-display-this",
                "api_key": "never-display-this-either",
                "prompt_text": "private prompt body",
                "codebook_content": "private codebook body",
            }
        ],
        "review": {"status": "ACCEPTED"},
    }


def _roundtrip(record: dict, path, backend: str):
    if backend == "json":
        path.write_text(json.dumps(record), encoding="utf-8")
    elif backend == "csv":
        flat = {
            key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            for key, value in record.items()
        }
        pd.DataFrame([flat]).to_csv(path, index=False)
    elif backend == "sqlite":
        flat = {
            key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            for key, value in record.items()
        }
        with sqlite3.connect(path) as con:
            pd.DataFrame([flat]).to_sql("annotations", con, index=False)
    else:  # pragma: no cover - test helper guard
        raise ValueError(backend)
    return load_frame(path)


def test_full_provenance_summary_exposes_safe_research_identifiers() -> None:
    record = _record()
    row = {
        **record,
        "source_country": "FI",
        "source_language": "fi",
        "review_status": "ACCEPTED",
        "model_runs": record["analysis"]["model_runs"],
        "codebook_refs": ["ai26-core"],
        "memory_refs": ["synthetic://context/legacy-memory-ref"],
        "raw_record": record,
    }
    summary = summarize_provenance(row)
    assert summary["run_id"] == "run-1"
    assert summary["study_id"] == "AI26"
    assert summary["context_profile"] == "balanced"
    assert summary["codebook_id"] == "ai26-core"
    assert summary["codebook_version"] == "2026.09"
    assert summary["codebook_hash"] == "cb-aaa"
    assert summary["model"] == "gemma4"
    assert summary["backend"] == "ollama"
    assert summary["execution_profile"] == "roihu"
    assert summary["rag_enabled"] is True
    assert summary["context_memory_enabled"] is True
    assert summary["validation_status"] == "ACCEPTED"
    assert summary["retrieval_ids"] == ["retrieval-9"]
    assert "synthetic://context/1" in summary["context_source_refs"]
    assert "synthetic://context/2" in summary["context_source_refs"]
    assert "synthetic://context/legacy-memory-ref" in summary["context_source_refs"]


def test_safe_event_projection_drops_secret_and_private_payload_values() -> None:
    row = {"provenance": _record()["provenance"]}
    events = safe_provenance_events(row)
    rendered = json.dumps(events, sort_keys=True)
    assert "run-1" in rendered
    assert "cfg-123" in rendered
    assert "never-display-this" not in rendered
    assert "private prompt body" not in rendered
    assert "private codebook body" not in rendered
    assert "password" not in rendered
    assert "api_key" not in rendered
    assert "prompt_text" not in rendered
    assert "codebook_content" not in rendered


def test_legacy_record_reports_unknown_instead_of_fabricating_provenance() -> None:
    summary = summarize_provenance(
        {
            "source_url": "synthetic://legacy",
            "source_country": "PL",
            "source_language": "pl",
            "review_status": "PROVISIONAL",
            "provenance": [],
        }
    )
    assert summary["run_id"] == UNKNOWN
    assert summary["codebook_hash"] == UNKNOWN
    assert summary["context_profile"] == UNKNOWN
    assert summary["country"] == "PL"
    assert summary["language"] == "pl"
    assert summary["validation_status"] == "PROVISIONAL"
    assert summary["rag_enabled"] is None
    assert summary["context_memory_enabled"] is None


def test_rag_enabled_and_disabled_are_preserved() -> None:
    enabled = summarize_provenance({"provenance": _record(rag=True)["provenance"]})
    disabled = summarize_provenance({"provenance": _record(rag=False)["provenance"]})
    assert enabled["rag_enabled"] is True
    assert disabled["rag_enabled"] is False


def test_mixed_run_codebook_and_config_versions_trigger_warning() -> None:
    rows = []
    for record in (_record("run-1", "cb-aaa"), _record("run-2", "cb-bbb")):
        rows.append(
            {
                "provenance": record["provenance"],
                "model_runs": record["analysis"]["model_runs"],
                "source_country": "FI",
                "source_language": "fi",
                "review_status": "PROVISIONAL",
                "raw_record": record,
            }
        )
    frame = pd.DataFrame(rows)
    mixed = mixed_provenance_dimensions(frame)
    assert mixed["run_id"] == ["run-1", "run-2"]
    assert mixed["codebook_hash"] == ["cb-aaa", "cb-bbb"]
    warning = comparison_warning(frame)
    assert warning is not None
    assert "run id" in warning
    assert "codebook hash" in warning


def test_provenance_projection_supports_json_csv_and_sqlite(tmp_path) -> None:
    cases = (
        ("json", tmp_path / "records.json"),
        ("csv", tmp_path / "records.csv"),
        ("sqlite", tmp_path / "records.sqlite3"),
    )
    for backend, path in cases:
        frame = _roundtrip(_record(), path, backend)
        projected = provenance_frame(frame)
        assert projected.iloc[0]["run_id"] == "run-1"
        assert projected.iloc[0]["context_profile"] == "balanced"
        assert projected.iloc[0]["codebook_hash"] == "cb-aaa"
        assert projected.iloc[0]["model"] == "gemma4"
        assert bool(projected.iloc[0]["rag_enabled"]) is True
