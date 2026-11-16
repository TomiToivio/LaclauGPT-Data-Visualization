"""The delivered EP24 export layout, and the audit that measures it (#405).

The 2026-11-15 delivery moved from one `combined.csv` to `<root>/<country>/<country>.csv` plus a
`children/` directory. The dashboard read only the old shape, so it reported "no export" against
correct data — a regression that no unit test caught because every fixture used the old layout.

These tests use the new layout end to end: reader, child tables, and the baseline audit.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from laclaugpt_visualization.ep24_children import load_children, statements, term_counts
from laclaugpt_visualization.ep24_reprocessed import read_records

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "ep24" / "audit_export_baseline.py"

PARENT_COLUMNS = ["_storage_id", "country", "dataset", "source_key", "video_id", "allas_filename",
                  "asr_transcript", "asr_model", "ocr_1", "frame_analysis_1", "vllm_video_analysis",
                  "summary_analysis", "postprocess_entities", "laclau_status", "laclau_summary_md",
                  "dna_status", "dna_statements_json", "sna_status", "sna_edges_json",
                  "rdf_status", "processing_status", "preprocess_status", "frame_analysis_status",
                  "vllm_video_status", "summary_quality_status", "video_status",
                  "video_quality_status", "created_at"]


def _audit_module():
    spec = importlib.util.spec_from_file_location("audit_export_baseline", AUDIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_export(root: Path, *, rows: int = 3, dna_rows: int = 2) -> Path:
    """A synthetic export in the 2026-11-15 layout, with one row carrying embedded newlines."""
    root.mkdir(parents=True, exist_ok=True)
    for country in ("finland", "poland", "portugal"):
        folder = root / country
        folder.mkdir(exist_ok=True)
        with (folder / f"{country}.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=PARENT_COLUMNS)
            writer.writeheader()
            for index in range(rows):
                writer.writerow({
                    "_storage_id": f"monday500:{country}:{index:04x}",
                    "country": country,
                    "dataset": "ep2024_reprocess",
                    "source_key": f"ep24:{country}:x:ig:v{index}",
                    "video_id": f"HEPP24-{country[:2].upper()}-IG-20240521-{index}",
                    "allas_filename": f"s3://example/{country}/{index}.mp4",
                    "asr_transcript": "line one\nline two\nline three" if index == 0 else "one line",
                    "asr_model": "whisper", "ocr_1": "on-screen", "frame_analysis_1": "a frame",
                    "vllm_video_analysis": "video text", "summary_analysis": "summary",
                    "postprocess_entities": '["Entity A"]', "laclau_status": "ok",
                    "laclau_summary_md": "laclau",
                    # DNA exists only for Finland in this fixture: a country with no step-7
                    # output must read as 0, not as "unknown".
                    "dna_status": "ok" if (country == "finland" and index < dna_rows) else "",
                    "dna_statements_json": "[]" if (country == "finland" and index < dna_rows) else "",
                    "sna_status": "ok" if country == "finland" else "",
                    "sna_edges_json": "[]" if country == "finland" else "",
                    "rdf_status": "", "processing_status": "OK", "preprocess_status": "ok",
                    "frame_analysis_status": "ok", "vllm_video_status": "ok",
                    "summary_quality_status": "OK", "video_status": "ok",
                    "video_quality_status": "ok", "created_at": "",
                })
    children = root / "children"
    children.mkdir(exist_ok=True)
    with (children / "entities.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["child_id", "source_key", "country", "field",
                                                    "index", "origin", "item.label"])
        writer.writeheader()
        for index in range(rows):
            writer.writerow({"child_id": str(index), "source_key": f"ep24:finland:x:ig:v{index}",
                             "country": "finland", "field": "postprocess_entities",
                             "index": "0", "origin": "summary", "item.label": "Entity A"})
    with (children / "dna_statements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["child_id", "source_key", "country",
                                                    "item.actor_name_raw", "item.concept_label_raw",
                                                    "item.evidence_quote"])
        writer.writeheader()
        for index in range(dna_rows):
            writer.writerow({"child_id": str(index), "source_key": f"ep24:finland:x:ig:v{index}",
                             "country": "finland", "item.actor_name_raw": f"Actor {index}",
                             "item.concept_label_raw": "the people",
                             "item.evidence_quote": "a quotation"})
    (root / "manifest.json").write_text(json.dumps({
        "producer_revision": "monday500_20261031",
        "exported_at": "2026-11-15T19:00:00+00:00",
        "countries": {"finland": {}, "poland": {}, "portugal": {}},
    }), encoding="utf-8")
    return root


def test_the_reader_concatenates_the_per_country_files(tmp_path):
    frame = read_records(write_export(tmp_path))
    assert len(frame) == 9
    assert sorted(frame["country"].unique()) == ["finland", "poland", "portugal"]
    assert frame["country"].value_counts().to_dict() == {"finland": 3, "poland": 3, "portugal": 3}


def test_embedded_newlines_do_not_become_extra_rows(tmp_path):
    root = write_export(tmp_path)
    frame = read_records(root)
    finland = frame[frame["country"] == "finland"]
    assert len(finland) == 3, "a transcript with newlines is one row, not three"


def test_child_tables_are_found_in_the_children_directory(tmp_path):
    children = load_children(write_export(tmp_path))
    assert len(children["entities"]) == 3
    assert term_counts(children["entities"])[0] == {"Term": "Entity A", "Videos / mentions": 3}
    assert len(statements(children["dna"])) == 2


def test_a_flat_export_still_reads(tmp_path):
    """The older layout must keep working: the reader supports both, not just the new one."""
    (tmp_path / "combined.csv").write_text(
        "country,video_id\nfinland,v1\npoland,v2\n", encoding="utf-8")
    frame = read_records(tmp_path)
    assert list(frame["country"]) == ["finland", "poland"]


def test_the_audit_counts_rows_by_parsing_not_by_lines(tmp_path):
    module = _audit_module()
    report = module.run(write_export(tmp_path))
    finland = next(row for row in report["countries"] if row["country"] == "finland")
    assert finland["rows"] == 3
    assert finland["rows_matching_header_width"] == 3
    assert finland["unique_identities"] == 3


def test_the_audit_reports_stage_population_per_country(tmp_path):
    module = _audit_module()
    report = module.run(write_export(tmp_path))
    finland = next(row for row in report["countries"] if row["country"] == "finland")
    poland = next(row for row in report["countries"] if row["country"] == "poland")
    assert finland["stages"]["7_dna"]["populated"] == 2
    assert poland["stages"]["7_dna"]["populated"] == 0
    assert finland["stages"]["8_sna"]["populated"] == 3
    assert poland["stages"]["8_sna"]["populated"] == 0, "an absent stage is zero, not invented"


def test_the_audit_finds_duplicate_identities(tmp_path):
    root = write_export(tmp_path)
    path = root / "poland" / "poland.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    rows[1]["_storage_id"] = rows[0]["_storage_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    module = _audit_module()
    poland = next(row for row in module.run(root)["countries"] if row["country"] == "poland")
    assert poland["duplicate_identities"] == 1
    assert poland["unique_identities"] == 2


def test_the_audit_checksum_expectation_fails_loudly(tmp_path, capsys):
    module = _audit_module()
    root = write_export(tmp_path)
    code = module.main(["--root", str(root), "--expect", "finland=" + "0" * 64 + ",1"])
    assert code == 1
    assert "sha256" in capsys.readouterr().err


def test_the_audit_emits_no_row_content(tmp_path):
    """The report is publishable: aggregate counts and column names, never a transcript."""
    module = _audit_module()
    report = module.run(write_export(tmp_path))
    serialised = json.dumps(report)
    assert "line one" not in serialised
    assert "a quotation" not in serialised
    assert "Actor 0" not in serialised
    assert module.markdown(report).count("|") > 10


def test_a_missing_country_is_reported_rather_than_silently_skipped(tmp_path):
    module = _audit_module()
    root = write_export(tmp_path)
    (root / "portugal" / "portugal.csv").unlink()
    report = module.run(root)
    portugal = next(row for row in report["countries"] if row["country"] == "portugal")
    assert portugal["present"] is False
    assert report["totals"]["countries_present"] == 2
