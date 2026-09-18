import json

import pytest

from laclaugpt import cli, mongo


def test_collection_name_and_status():
    assert mongo.collection_name("ai26") == "laclaugpt2_ai26_scraper_collection"
    assert mongo.analysis_status({"phase0": {"discourse": {"status": "ok"}}}) == "analyzed"
    assert mongo.analysis_status({"phase0": {"discourse": {"status": "error"}}}) == "error"
    assert mongo.analysis_status({}) == "awaiting"


def test_settings_accept_shared_phase0_environment(monkeypatch):
    monkeypatch.setenv("LACLAUGPT_MONGODB_URI", "mongodb://example")
    monkeypatch.setenv("LACLAUGPT_MONGODB_DATABASE", "laclaugpt")
    monkeypatch.setenv("LACLAUGPT_PROJECT_ID", "ai26")
    assert mongo.settings() == ("mongodb://example", "laclaugpt", "ai26")


def test_settings_fail_plainly(monkeypatch):
    for key in (
        "LACLAUGPT_MONGODB_URI",
        "MONGO_URI",
        "LACLAUGPT_MONGODB_DATABASE",
        "MONGO_DB_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        mongo.settings()


def test_build_query():
    assert mongo.build_query(status="analyzed", arena="elites", language="en") == {
        "phase0.discourse.status": "ok",
        "arena": "elites",
        "language": "en",
    }
    assert mongo.build_query(since="2026-01-01", until="2026-12-31") == {
        "source_date": {"$gte": "2026-01-01", "$lte": "2026-12-31"}
    }


def test_cli_list_without_records_is_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "list_documents", lambda **kwargs: [])
    assert cli.main(["list"]) == 0
    assert "phase0.discourse.status" in capsys.readouterr().out


def test_cli_list_marks_awaiting_and_exposes_errors(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "list_documents",
        lambda **kwargs: [
            {"source_url": "https://example.test/waiting"},
            {
                "source_url": "https://example.test/error",
                "phase0": {"discourse": {"status": "error", "error": "model timeout"}},
            },
        ],
    )
    assert cli.main(["list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["phase0.discourse.status"] == "awaiting analysis"
    assert payload[0]["analysis_status"] == "awaiting"
    assert payload[1]["phase0.discourse.status"] == "error"
    assert payload[1]["analysis_status"] == "error"


def test_cli_inspect_by_identity_shows_analysis_sections(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "find_document",
        lambda identity: {
            "_id": "private-backend-id",
            "document_id": "doc-1",
            "source_url": identity,
            "source_title": "Title",
            "text": "Full source text",
            "phase0_summary": {"status": "ok", "summary": "Validated summary"},
            "phase0": {"discourse": {"status": "error", "error": "model timeout"}},
            "phase0_discourse": {"nodal_points": ["AI"]},
            "phase0_ontology": {"entities": ["OpenAI"]},
        },
    )
    assert cli.main(["inspect", "https://example.test/a", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_url"] == "https://example.test/a"
    assert payload["text"] == "Full source text"
    assert payload["phase0_summary"]["summary"] == "Validated summary"
    assert payload["phase0_discourse"]["nodal_points"] == ["AI"]
    assert payload["phase0_ontology"]["entities"] == ["OpenAI"]
    assert payload["phase0"]["discourse"]["error"] == "model timeout"
    assert payload["analysis_status"] == "error"
    assert "_id" not in payload


def test_cli_inspect_missing_document_is_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_document", lambda identity: None)
    assert cli.main(["inspect", "missing"]) == 1
    assert "document not found" in capsys.readouterr().err


def test_cli_configuration_failure_is_nonzero(monkeypatch, capsys):
    def fail(**kwargs):
        raise RuntimeError("LACLAUGPT_MONGODB_URI is required")

    monkeypatch.setattr(cli, "list_documents", fail)
    assert cli.main(["list"]) == 2
    assert "MONGODB_URI" in capsys.readouterr().err


def test_jsonl_export_preserves_nested_analysis(tmp_path):
    path = tmp_path / "phase0.jsonl"
    document = {
        "source_url": "https://example.test/a",
        "phase0_discourse": {"signifiers": ["AI"]},
    }
    cli._export([document], path, "jsonl")
    assert json.loads(path.read_text())["phase0_discourse"]["signifiers"] == ["AI"]
