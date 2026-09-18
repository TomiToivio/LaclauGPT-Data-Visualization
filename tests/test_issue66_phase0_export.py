import csv
import json

import pytest

from laclaugpt_visualization.phase0_export import (
    CSV_FIELDS,
    DEFAULT_EXPORT_DIR,
    export_phase0,
)
from laclaugpt_visualization.phase0_mongo import normalize_phase0_record


@pytest.fixture
def records():
    raw = [
        {
            "_id": "mongo-only",
            "source_url": "https://example.test/a",
            "source_date": "2026-09-18T12:00:00Z",
            "source_name": "Example Feed",
            "source_title": "Example",
            "source_author": "Author",
            "actor_name": "OpenAI",
            "arena": "labs",
            "ai_formation": "accelerationist",
            "language": "en",
            "phase0": {
                "discourse": {"status": "ok", "signals": {"beta": 2, "alpha": 1}},
                "summary": {"status": "ok"},
            },
            "phase0_summary": {"summary": "A"},
            "phase0_discourse": {"signifiers": ["AI"], "scores": {"b": 2, "a": 1}},
            "phase0_ontology": {"entities": [{"label": "OpenAI", "kind": "org"}]},
        }
    ]
    return [normalize_phase0_record(record) for record in raw]


def test_jsonl_export_preserves_nested_phase0_and_source_url(records, tmp_path):
    path = tmp_path / "selected.jsonl"

    output = export_phase0(records, fmt="jsonl", path=path)

    assert output == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source_url"] == "https://example.test/a"
    assert payload["phase0"]["discourse"]["signals"] == {"alpha": 1, "beta": 2}
    assert payload["phase0_discourse"]["signifiers"] == ["AI"]
    assert "_id" not in payload


def test_jsonl_nested_encoding_is_deterministic(records, tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"

    export_phase0(records, fmt="jsonl", path=first)
    export_phase0(records, fmt="jsonl", path=second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert '"signals":{"alpha":1,"beta":2}' in first.read_text(encoding="utf-8")


def test_csv_export_is_small_and_deterministic(records, tmp_path):
    path = tmp_path / "selected.csv"

    export_phase0(records, fmt="csv", path=path)

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert tuple(row) == CSV_FIELDS
    assert row["source_url"] == "https://example.test/a"
    assert row["analysis_status"] == "analyzed"
    assert row["phase0_discourse"] == '{"scores":{"a":1,"b":2},"signifiers":["AI"]}'
    assert json.loads(row["phase0"]) == records[0]["phase0"]


@pytest.mark.parametrize(
    ("fmt", "filename"),
    [("jsonl", "phase0.jsonl"), ("csv", "phase0.csv")],
)
def test_default_output_is_data_exports(records, tmp_path, monkeypatch, fmt, filename):
    monkeypatch.chdir(tmp_path)

    output = export_phase0(records, fmt=fmt)

    assert output == DEFAULT_EXPORT_DIR / filename
    assert (tmp_path / output).exists()


def test_export_rejects_unknown_format(records):
    with pytest.raises(ValueError, match="format must be"):
        export_phase0(records, fmt="xml")
