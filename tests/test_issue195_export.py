"""Synthetic tests only; no real political records or operational credentials."""
import csv
import json
import sqlite3

import pytest

from laclaugpt_visualization.ep24_export import (
    child_tables,
    main,
    project,
    read_source,
    write_bundle,
)


def row(country="finland", **changes):
    return {
        "country": country, "video_id": "00042", "source_type": "synthetic",
        "_storage_id": "store-42", "asr_transcript": "Synthetic source quotation",
        "entities": '["Researcher annotation"]',
        "postprocess_entities": '["Model annotation"]',
        "sna_status": "no_evidence", "sna_edges_json": "[]",
        "rdf_status": "warning", "rdf_document_uri": "urn:synthetic:42",
        "laclau_status": "error", "laclau_abstention_reason": "Insufficient evidence",
        "dna_statements_json": json.dumps(json.dumps([{
            "statement_id": "same-local-id", "actor": "Synthetic actor", "concept": "Test",
            "evidence_quote": "Synthetic source quotation", "agreement": None,
        }])),
        "_pipeline": {"step_06": {"status": "retry", "run_id": "omit-transient"}},
        "laclau_raw_response": "OMIT_RAW", "vllm_video_prompt": "OMIT_PROMPT",
        "backend_uri": "OMIT_BACKEND", **changes,
    }


def source(records, country="finland"):
    return (country, "synthetic-checkpoint", records)


def test_namespace_and_preserve_human_machine_and_status():
    records, qa, omitted, _ = project([source([row()]), source([row("poland")], "poland")])
    assert len(records) == 2 and not qa
    assert records[0]["source_key"] != records[1]["source_key"]
    fields = records[0]["fields"]
    assert fields["video_id"] == "00042"
    assert fields["entities"] == ["Researcher annotation"]
    assert fields["postprocess_entities"] == ["Model annotation"]
    assert fields["dna_statements_json"][0]["agreement"] is None
    assert records[0]["stages"]["6"]["reported_status"] == "error"
    assert records[0]["stages"]["6"]["execution"] == {"status": "retry"}
    assert records[0]["stages"]["8"]["reported_status"] == "no_evidence"
    assert records[0]["stages"]["9"]["reported_status"] == "warning"
    assert "backend_uri" in omitted and "laclau_raw_response" in omitted
    assert "OMIT_" not in json.dumps(records)


@pytest.mark.parametrize("bad", [None, "", "nan", 42, 42.0])
def test_bad_identifiers_are_quarantined(bad):
    records, qa, _, _ = project([source([row(video_id=bad)])])
    assert records == []
    assert qa[0]["reason"] == "missing_or_nonstring_video_id"


def test_country_mismatch_and_platform_are_quarantined():
    records, qa, _, _ = project([source([row("poland"), row(source_type="")])])
    assert records == []
    assert {q["reason"] for q in qa} == {"missing_or_conflicting_country", "missing_platform"}


def test_conflicting_duplicates_never_select_arbitrary_winner():
    records, qa, _, _ = project([source([row(), row(asr_transcript="Different final result")])])
    assert records == [] and qa[0]["reason"] == "conflicting_duplicate"
    records, qa, _, _ = project([source([row(), row()])])
    assert len(records) == 1 and len(records[0]["provenance"]) == 2
    assert qa[0]["reason"] == "identical_duplicate"


def test_child_identity_evidence_and_country_roundtrip():
    records, *_ = project([source([row()]), source([row("portugal")], "portugal")])
    children = child_tables(records)["dna_statements"]
    assert len({r["child_id"] for r in children}) == 2
    parents = {r["source_key"]: r for r in records}
    for child in children:
        parent = parents[child["source_key"]]
        assert child["value"]["evidence_quote"] == parent["fields"]["asr_transcript"]
        assert child["country"] == parent["fields"]["country"]


def test_malformed_json_is_retained_and_reported():
    records, qa, _, _ = project([source([row(dna_statements_json="{broken")])])
    assert records[0]["fields"]["dna_statements_json"] == "{broken"
    assert qa[0]["reason"] == "malformed_structured_field"
    assert child_tables(records)["dna_statements"] == []


def test_csv_sqlite_and_jsonl_equivalent_and_read_only(tmp_path):
    original = row()
    serial = {k: json.dumps(v) if isinstance(v, dict) else v for k, v in original.items()}
    csv_path = tmp_path / "input.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=serial)
        writer.writeheader()
        writer.writerow(serial)
    sql_path = tmp_path / "input.sqlite3"
    with sqlite3.connect(sql_path) as db:
        db.execute("CREATE TABLE records (" + ",".join(f'"{k}" TEXT' for k in serial) + ")")
        db.execute("INSERT INTO records VALUES (" + ",".join("?" for _ in serial) + ")",
                   list(serial.values()))
    json_path = tmp_path / "input.jsonl"
    json_path.write_text(json.dumps(original) + "\n")
    projected = []
    for path in (csv_path, sql_path, json_path):
        before = path.read_bytes()
        projected.append(project([source(read_source(path))])[0])
        assert path.read_bytes() == before
    assert projected[0] == projected[1] == projected[2]
    with pytest.raises(ValueError, match="table"):
        read_source(sql_path, 'records"; DROP TABLE records;--')


def test_bundle_reproducible_private_and_complete(tmp_path):
    inputs = [source([row(c)], c) for c in ("finland", "poland", "portugal")]
    for name in ("a", "b"):
        manifest = write_bundle(tmp_path / name, inputs, exported_at="2026-01-01T00:00:00Z")
        assert manifest["all_requested_countries_present"]
        assert manifest["countries"]["portugal"]["exported_videos"] == 1
        assert (tmp_path / name).stat().st_mode & 0o077 == 0
    for file in (tmp_path / "a").iterdir():
        assert file.read_bytes() == (tmp_path / "b" / file.name).read_bytes()
    assert b"OMIT_PROMPT" not in (tmp_path / "a" / "combined.jsonl").read_bytes()
    with pytest.raises(ValueError, match="new directory"):
        write_bundle(tmp_path / "a", inputs)


def test_cli_incomplete_countries_and_formula_protection(tmp_path):
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps(row(author_username="=SUM(1,2)")) + "\n")
    output = tmp_path / "export"
    assert main(["--input", f"fi={path}", "--output", str(output)]) == 2
    with (output / "finland.csv").open(encoding="utf-8-sig") as f:
        assert next(csv.DictReader(f))["author_username"] == "'=SUM(1,2)"
    assert json.loads((output / "finland.jsonl").read_text())["fields"]["author_username"] == "=SUM(1,2)"


def test_mongo_adapter_only_reads_allowlisted_country_collections(monkeypatch):
    import sys
    from types import SimpleNamespace

    from laclaugpt_visualization.ep24_export import read_mongo

    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __getitem__(self, key):
            calls.append(key)
            return self

        def find(self, query, projection):
            assert query == {}
            assert projection["_id"] == 0
            assert "vllm_video_prompt" not in projection
            assert "_pipeline" in projection
            return [row()]

    monkeypatch.setitem(sys.modules, "pymongo", SimpleNamespace(MongoClient=Client))
    result = read_mongo("synthetic-unused", "synthetic-db", ["finland"])
    assert calls == ["synthetic-db", "laclaugpt_ep2024_reprocess_finland_dataframe"]
    assert result[0][0] == "finland"
    assert len(result[0][1]) == 64


def test_thousand_record_export_and_human_readable_evidence(tmp_path):
    inputs = [source([row(video_id=f"synthetic-{i}") for i in range(1000)])]
    manifest = write_bundle(tmp_path / "large", inputs)
    assert manifest["countries"]["finland"]["exported_videos"] == 1000
    report = (tmp_path / "large" / "finland.md").read_text()
    assert "Synthetic source quotation" in report
    assert "Researcher annotation" in report and "Model annotation" in report
    assert "OMIT_PROMPT" not in report
