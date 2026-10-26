"""Issue #195 Part 1: the export must be read-only, namespaced, allowlisted and honest.

Every test here maps to a line in the issue's Part 1 checklist. The fixtures are synthetic:
no real videos, no credentials, no restricted media — the real export belongs in the private
repository.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ep24" / "export_visualization_data.py"
FIXTURES = ROOT / "tests" / "fixtures" / "ep24_export"

sys.path.insert(0, str(SCRIPT.parent))


def run_export(tmp_path: Path, countries=("finland", "poland", "portugal")) -> Path:
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--countries", *countries,
         "--input", str(FIXTURES), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return output


def qa(output: Path) -> dict:
    return json.loads((output / "qa.json").read_text(encoding="utf-8"))


def test_exports_the_files_the_dashboard_already_reads(tmp_path: Path) -> None:
    """The dashboard looks for combined.csv / <country>.csv / records.jsonl; nothing else."""
    output = run_export(tmp_path)
    for name in ("combined.csv", "finland.csv", "poland.csv", "records.jsonl", "qa.json",
                 "DATA_DICTIONARY.md"):
        assert (output / name).is_file(), name


def test_country_namespaces_never_merge(tmp_path: Path) -> None:
    """FI video 1 and PL video 1 are different records, not a join."""
    rows = list(csv.DictReader((run_export(tmp_path) / "combined.csv").open(encoding="utf-8")))
    ids = [row["record_id"] for row in rows]
    assert len(ids) == len(set(ids))
    fi = [i for i in ids if "finland" in i]
    pl = [i for i in ids if "poland" in i]
    assert fi and pl, ids
    assert set(fi).isdisjoint(pl)


def test_a_row_without_identity_is_excluded_and_counted(tmp_path: Path) -> None:
    report = qa(run_export(tmp_path))
    finland = report["countries"]["finland"]
    assert finland["invalid_identity"] == 1
    assert finland["kept"] == 2, "the identity-less row must not be exported"
    rows = list(csv.DictReader((tmp_path / "export" / "finland.csv").open(encoding="utf-8")))
    assert all(row["record_id"] for row in rows)
    assert "No identity at all" not in {row.get("title") for row in rows}


def test_transient_backend_fields_are_dropped(tmp_path: Path) -> None:
    output = run_export(tmp_path)
    text = (output / "combined.csv").read_text(encoding="utf-8")
    assert "TRANSIENT-PROMPT" not in text
    assert "TENSOR-BLOB" not in text
    dictionary = (output / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    assert "prompt" in dictionary and "transient model prompt" in dictionary


def test_one_to_many_becomes_child_tables_with_stable_ids(tmp_path: Path) -> None:
    output = run_export(tmp_path)
    dna = list(csv.DictReader((output / "dna_statements.csv").open(encoding="utf-8")))
    sna = list(csv.DictReader((output / "sna_edges.csv").open(encoding="utf-8")))
    assert len(dna) == 2 and len(sna) == 1
    for row in dna + sna:
        assert row["parent_record_id"]
        assert row["child_id"].startswith(row["parent_record_id"] + "#")
    assert {row["actor"] for row in dna} == {"A", "B"}


def test_a_missing_country_is_empty_not_zero_findings(tmp_path: Path) -> None:
    """Portugal has no fixture: it must be reported as absent, never as 'no phenomenon'."""
    report = qa(run_export(tmp_path))
    portugal = report["countries"]["portugal"]
    assert portugal["found"] is False
    assert "not as zero findings" in portugal["note"]
    assert report["rows"]["by_country"]["portugal"] == 0


def test_a_failed_stage_stays_visible_and_is_not_success(tmp_path: Path) -> None:
    rows = list(csv.DictReader((run_export(tmp_path) / "finland.csv").open(encoding="utf-8")))
    failed = [row for row in rows if row["title"] == "Synthetic FI two"]
    assert failed, "a failed row must still be exported"
    assert failed[0]["laclau_status"] == "failed"
    assert failed[0]["error_status"] == "failed"


def test_stage_coverage_counts_only_what_is_present(tmp_path: Path) -> None:
    coverage = qa(run_export(tmp_path))["stage_coverage"]
    assert coverage["0"]["present"] == 3, "three rows carry identity fields"
    assert coverage["6"]["present"] == 1, "only one row has laclau output"
    assert coverage["9"]["present"] is None, "stage 9 is a file artifact, never inferred"


def test_the_export_is_deterministic(tmp_path: Path) -> None:
    first = run_export(tmp_path / "a")
    second = run_export(tmp_path / "b")
    for name in ("combined.csv", "records.jsonl", "finland.csv", "qa.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_the_source_tree_is_untouched(tmp_path: Path) -> None:
    before = {p.name: p.stat().st_mtime_ns for p in FIXTURES.iterdir()}
    run_export(tmp_path)
    after = {p.name: p.stat().st_mtime_ns for p in FIXTURES.iterdir()}
    assert before == after, "export must be read-only on its source"


def test_no_credentials_or_real_data_in_the_repository(tmp_path: Path) -> None:
    output = run_export(tmp_path)
    blob = "".join(p.read_text(encoding="utf-8") for p in output.iterdir() if p.is_file())
    for forbidden in ("mongodb://", "redis://", "password", "secret", "api_key"):
        assert forbidden not in blob.lower()
