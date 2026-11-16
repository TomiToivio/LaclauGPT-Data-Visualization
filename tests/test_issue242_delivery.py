"""Synthetic regression tests for researcher privacy, evidence and explicit cohort scope."""
import csv
import gzip
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from laclaugpt_visualization.ep24_cohort import is_member, read_roster
from laclaugpt_visualization.ep24_presentation import (
    hydrate_record,
    researcher_csv,
    researcher_frame,
)

ROOT = Path(__file__).resolve().parents[1]


def test_default_export_excludes_internal_and_nested_debug_values():
    frame = pd.DataFrame([{"country": "fi", "_storage_id": "PRIVATE-ID", "prompt": "SECRET",
                           "title": "=HYPERLINK(\"bad\")",
                           "postprocess_entities": '[{"name":"Alice","prompt":"SECRET"}]'}])
    safe = researcher_frame(frame)
    assert safe.iloc[0]["Country"] == "Finland"
    assert safe.iloc[0]["Entities"] == "• Name: Alice"
    exported = researcher_csv(frame).decode("utf-8-sig")
    assert "SECRET" not in exported and "PRIVATE-ID" not in exported
    assert "'=HYPERLINK" in exported
    assert "prompt" not in exported


@pytest.mark.parametrize("key,nested", [("record_id", False), ("record_key", True)])
def test_full_evidence_restored_only_for_selected_record(tmp_path, key, nested):
    full = {"asr_transcript": "Full original evidence", "prompt": "SECRET"}
    payload = {key: "fi:test", **({"1_preprocess": full} if nested else full)}
    with gzip.open(tmp_path / "finland_text.jsonl.gz", "wt") as handle:
        handle.write(json.dumps(payload) + "\n")
    result = hydrate_record(tmp_path, {key: "fi:test", "title": "Example"})
    assert result["asr_transcript"] == full["asr_transcript"]
    assert "prompt" not in result
    assert "asr_transcript" not in hydrate_record(tmp_path, {key: "fi:other"})


def make_roster(path):
    path.write_text("\n".join(f"monday500:{c}:synthetic-{i}" for c in
                              ("finland", "poland", "portugal") for i in range(500)))
    return read_roster(path)


def test_roster_rejects_wrong_country_dataset_and_unapproved_rows(tmp_path):
    approved, manifest = make_roster(tmp_path / "roster.txt")
    assert manifest["approved_counts"] == dict.fromkeys(("finland", "poland", "portugal"), 500)
    row = {"_storage_id": "monday500:finland:synthetic-0", "country": "Finland"}
    assert is_member(row, "finland", approved)
    assert not is_member(row, "poland", approved)
    # The per-row dataset label is the producer's pipeline label, not cohort identity (#242):
    # membership is the roster + storage key + country.
    assert is_member({**row, "dataset": "ep2024_reprocess"}, "finland", approved)
    assert not is_member({**row, "_storage_id": "full-corpus"}, "finland", approved)
    (tmp_path / "roster.txt").write_text("monday500:finland:synthetic-0\n")
    with pytest.raises(ValueError, match="exactly 500"):
        read_roster(tmp_path / "roster.txt")


def test_roster_applies_before_duplicate_selection(tmp_path):
    import sys
    spec = importlib.util.spec_from_file_location("export242", ROOT / "scripts/ep24/export_streaming.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = tmp_path / "finland.csv"
    approved, _ = make_roster(tmp_path / "roster.txt")
    with source.open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=["_storage_id", "country", "allas_filename", "summary_analysis"])
        writer.writeheader()
        writer.writerow({"_storage_id": "full-corpus", "country": "Finland",
                         "allas_filename": "https://example.invalid/video", "summary_analysis": "unapproved"})
        writer.writerow({"_storage_id": "monday500:finland:synthetic-0", "country": "finland",
                         "allas_filename": "https://example.invalid/video"})
    winners, _ = module.select_primary_rows(source, "finland", "reprocessed", None, None, approved=approved)
    assert list(winners.values()) == [1]


def test_app_default_and_browser_do_not_show_internal_values(tmp_path, monkeypatch):
    pd.DataFrame([{"country": "finland", "video_id": "synthetic", "_storage_id": "SECRET",
                   "title": "Test video", "source_type": "tiktok", "source_language": "fi",
                   "source_url": "https://example.invalid/video"}]).to_csv(tmp_path / "combined.csv", index=False)
    monkeypatch.setenv("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LACLAUGPT_VIS_DEMO_PASSWORD", raising=False)
    app = AppTest.from_file(str(ROOT / "src/laclaugpt_visualization/ep24_reprocessed_app.py"))
    app.run(timeout=30)
    assert not app.exception
    assert not app.json
    next(r for r in app.sidebar.radio if r.label == "Research view").set_value("Video browser").run()
    assert not app.exception
    assert "SECRET" not in str(app.dataframe[0].value)


def test_nested_streaming_dna_bundle_is_joined(tmp_path):
    from laclaugpt_visualization.ep24_reprocessed import dna_evidence
    parent = {"country": "finland", "video_id": "synthetic", "record_key": "fi:video"}
    with gzip.open(tmp_path / "finland_text.jsonl.gz", "wt") as handle:
        handle.write(json.dumps({"record_key": "fi:video", "7_dna": {
            "dna_statements_json": [{"actor": "A", "concept": "B", "evidence_quote": "C"}]}}) + "\n")
    result = dna_evidence([parent], tmp_path)
    assert result.statements == 1
    assert result.items[0]["actor"] == "A"


def test_display_schema_matches_implementation():
    from laclaugpt_visualization.ep24_presentation import DETAIL_KEYS, DISPLAY_VERSION, FIELDS
    schema = json.loads((ROOT / "schemas/ep24_researcher_display_v1.json").read_text())
    assert schema == {"version": DISPLAY_VERSION, "fields": FIELDS,
                      "nested_allowed_keys": sorted(DETAIL_KEYS)}


def test_all_country_children_survive_one_export(tmp_path):
    import sys
    spec = importlib.util.spec_from_file_location("export242children", ROOT / "scripts/ep24/export_streaming.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    args = []
    for country in ("finland", "poland", "portugal"):
        source = tmp_path / f"{country}.csv"
        with source.open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=["_storage_id", "country", "postprocess_entities"])
            writer.writeheader()
            writer.writerow({"_storage_id": f"synthetic-{country}", "country": country,
                             "postprocess_entities": json.dumps([{"name": country}])})
        args.extend(["--source", f"{country}={source}"])
    output = tmp_path / "export"
    assert module.main([*args, "--output", str(output)]) == 0
    children = list(csv.DictReader((output / "entities.csv").open()))
    assert len(children) == 3
    assert {row["label"] for row in children} == {"finland", "poland", "portugal"}


def test_authenticated_researcher_entrypoint_with_verified_roster(tmp_path, monkeypatch):
    approved, cohort = make_roster(tmp_path / "roster.txt")
    pd.DataFrame([{"_storage_id": value, "video_id": value, "country": value.split(":")[1],
                   "source_type": "synthetic", "title": "Synthetic video"}
                  for value in sorted(approved)]).to_csv(tmp_path / "combined.csv", index=False)
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"approved_cohort": cohort}))
    monkeypatch.setenv("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LACLAUGPT_VIS_DEMO_PASSWORD", "synthetic-test-only")
    monkeypatch.setenv("EP24_APPROVED_ROSTER", str(tmp_path / "roster.txt"))
    app = AppTest.from_file(str(ROOT / "src/laclaugpt_visualization/ep24_researcher_app.py"))
    app.session_state["demo_authenticated"] = True
    app.run(timeout=30)
    assert not app.exception
    assert not app.error
    labels = [tab.label for tab in app.tabs]
    assert labels[:8] == ["Overview", "Videos & multimodal evidence", "Entities and themes",
                          "Laclau discourse", "DNA", "SNA", "Multilayer", "RDF & methods"]
    assert "Legacy analytics" in labels and "Export" in labels, "the merged tabs must be present"
    assert any("match the export" in str(message.value) for message in app.success), \
        "a verified roster must report success, not merely avoid errors"
