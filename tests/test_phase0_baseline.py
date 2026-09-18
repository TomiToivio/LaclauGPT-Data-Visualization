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
    for key in ("LACLAUGPT_MONGODB_URI", "MONGO_URI", "LACLAUGPT_MONGODB_DATABASE", "MONGO_DB_NAME"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        mongo.settings()


def test_build_query():
    assert mongo.build_query(status="analyzed", arena="elites", language="en") == {
        "phase0.discourse.status": "ok", "arena": "elites", "language": "en"
    }
    assert mongo.build_query(since="2026-01-01", until="2026-12-31") == {
        "source_date": {"$gte": "2026-01-01", "$lte": "2026-12-31"}
    }


def test_cli_list_without_records_is_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "list_documents", lambda **kwargs: [])
    assert cli.main(["list"]) == 0
    assert "analysis_status" in capsys.readouterr().out


def test_cli_inspect(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_document", lambda identity: {
        "_id": "private-backend-id", "source_url": identity,
        "phase0": {"discourse": {"status": "ok"}}, "phase0_discourse": {"nodal_points": ["AI"]},
    })
    assert cli.main(["inspect", "https://example.test/a"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_url"] == "https://example.test/a"
    assert payload["analysis_status"] == "analyzed"
    assert "_id" not in payload


def test_jsonl_export_preserves_nested_analysis(tmp_path):
    path = tmp_path / "phase0.jsonl"
    document = {"source_url": "https://example.test/a", "phase0_discourse": {"signifiers": ["AI"]}}
    cli._export([document], path, "jsonl")
    assert json.loads(path.read_text())["phase0_discourse"]["signifiers"] == ["AI"]
