import csv
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
    assert "analysis_status" in capsys.readouterr().out


def test_cli_inspect(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "find_document",
        lambda identity: {
            "_id": "private-backend-id",
            "source_url": identity,
            "phase0": {"discourse": {"status": "ok"}},
            "phase0_discourse": {"nodal_points": ["AI"]},
        },
    )
    assert cli.main(["inspect", "https://example.test/a"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_url"] == "https://example.test/a"
    assert payload["analysis_status"] == "analyzed"
    assert "_id" not in payload


def test_jsonl_export_preserves_nested_analysis_and_identity(tmp_path):
    path = tmp_path / "phase0.jsonl"
    document = {
        "_id": "backend-only",
        "source_url": "https://example.test/a",
        "phase0": {"discourse": {"status": "ok", "signals": {"beta": 2, "alpha": 1}}},
        "phase0_discourse": {"signifiers": ["AI"]},
    }

    cli._export([document], path, "jsonl")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source_url"] == "https://example.test/a"
    assert payload["phase0"]["discourse"]["signals"] == {"alpha": 1, "beta": 2}
    assert payload["phase0_discourse"]["signifiers"] == ["AI"]
    assert "_id" not in payload


def test_jsonl_export_is_deterministic_for_nested_values(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    document = {
        "source_url": "https://example.test/a",
        "phase0": {"z": 1, "a": {"y": 2, "x": 1}},
    }

    cli._export([document], first, "jsonl")
    cli._export([document], second, "jsonl")

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert '"phase0":{"a":{"x":1,"y":2},"z":1}' in first.read_text(encoding="utf-8")


def test_csv_export_uses_small_flat_schema_and_deterministic_nested_json(tmp_path):
    path = tmp_path / "phase0.csv"
    document = {
        "_id": "backend-only",
        "source_url": "https://example.test/a",
        "source_title": "Example",
        "arena": "elites",
        "phase0": {"discourse": {"status": "ok"}, "z": 2, "a": 1},
        "phase0_discourse": {"signifiers": ["AI"], "scores": {"b": 2, "a": 1}},
        "phase0_ontology": {"entities": [{"label": "OpenAI", "kind": "org"}]},
    }

    cli._export([document], path, "csv")

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert row["source_url"] == "https://example.test/a"
    assert row["analysis_status"] == "analyzed"
    assert json.loads(row["phase0"]) == document["phase0"]
    assert row["phase0"] == '{"a":1,"discourse":{"status":"ok"},"z":2}'
    assert row["phase0_discourse"] == '{"scores":{"a":1,"b":2},"signifiers":["AI"]}'
    assert "_id" not in row


def test_cli_export_defaults_to_data_exports(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    document = {
        "source_url": "https://example.test/a",
        "phase0": {"discourse": {"status": "ok"}},
    }
    monkeypatch.setattr(cli, "list_documents", lambda **kwargs: [document])

    assert cli.main(["export", "--format", "jsonl"]) == 0

    output = tmp_path / "data" / "exports" / "phase0.jsonl"
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["source_url"] == document["source_url"]
    assert capsys.readouterr().out.strip() == "data/exports/phase0.jsonl"
