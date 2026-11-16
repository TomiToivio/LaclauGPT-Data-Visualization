"""The deployment verifier itself (issue #242).

A verifier that cannot fail is decoration. These tests build broken deployments on purpose and
assert that each one is reported: a manifest whose totals disagree with itself, a CSV whose rows do
not match the manifest, a producer column nobody classified, and a checkout serving modified code.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ep24" / "verify_researcher_dashboard.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_researcher_dashboard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _load()

COLUMNS = ["record_id", "country", "video_id", "asr_model", "_storage_id", "asr_runtime_ms"]

MANIFEST = {
    "contract": "ep24-reprocessed-view/0.1",
    "dataset": "ep24_monday500_20261031",
    "records": 1500,
    "record_counts": {
        "exported_total": 1500,
        "finland": {"exported": 500},
        "poland": {"exported": 500},
        "portugal": {"exported": 500},
    },
    "countries": {
        "finland": {"coverage": {"step_01": {"complete": 500}, "step_07": {"complete": 500}}},
        "poland": {"coverage": {"step_01": {"complete": 500}, "step_07": {"complete": 0}}},
        "portugal": {"coverage": {"step_01": {"complete": 500}, "step_07": {"complete": 0}}},
    },
}


def build(tmp_path: Path, *, rows: int = 1500, columns: list[str] | None = None,
          manifest: dict | None = None) -> Path:
    root = tmp_path / "artifacts"
    root.mkdir()
    header = columns or COLUMNS
    with (root / "combined.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index in range(rows):
            writer.writerow([f"fi/{index}", "finland", str(index), "whisper", "s1", "900"][: len(header)])
    (root / "MANIFEST.json").write_text(json.dumps(manifest or MANIFEST), encoding="utf-8")
    for country in ("finland", "poland", "portugal"):
        (root / f"{country}_text.jsonl.gz").write_bytes(b"")
    return root


def status(results: list[dict], name: str) -> str:
    return next(item["status"] for item in results if item["check"] == name)


def test_a_complete_deployment_passes_every_check(tmp_path):
    root = build(tmp_path)
    manifest, results = VERIFY.check_manifest(root)
    results += VERIFY.check_artifacts(root, manifest)
    results += VERIFY.check_coverage(manifest)
    failures = [item for item in results if item["status"] == "FAIL"]
    assert failures == []


def test_manifest_totals_that_disagree_are_a_failure(tmp_path):
    broken = {**MANIFEST, "records": 1499}
    root = build(tmp_path, manifest=broken)
    _, results = VERIFY.check_manifest(root)
    assert status(results, "manifest totals agree") == "FAIL"


def test_a_row_count_that_differs_from_the_manifest_is_a_failure(tmp_path):
    root = build(tmp_path, rows=1400)
    manifest, _ = VERIFY.check_manifest(root)
    results = VERIFY.check_artifacts(root, manifest)
    assert status(results, "combined.csv row count") == "FAIL"
    assert "1400" in next(item["detail"] for item in results if item["check"] == "combined.csv row count")


def test_an_unclassified_producer_column_fails_the_deployment_check(tmp_path):
    """With the live-steps allowlist selected, an unclassified column must fail the check."""
    root = build(tmp_path, columns=[*COLUMNS, "brand_new_producer_field"])
    manifest, _ = VERIFY.check_manifest(root)
    results = VERIFY.check_artifacts(root, manifest, allowlist="research")
    assert status(results, "column allowlist") == "FAIL"
    assert "brand_new_producer_field" in next(
        item["detail"] for item in results if item["check"] == "column allowlist"
    )


def test_coverage_is_reported_per_country_and_a_zero_stage_stays_visible(tmp_path):
    results = VERIFY.check_coverage(MANIFEST)
    poland = next(item for item in results if item["check"] == "coverage · poland")
    assert "step_07=0" in poland["detail"]


def test_a_manifest_without_coverage_fails(tmp_path):
    results = VERIFY.check_coverage({"records": 1500})
    assert results[0]["status"] == "FAIL"


def test_a_checkout_with_modified_files_is_not_the_commit(tmp_path):
    repo = tmp_path / "served"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    clean = VERIFY.check_checkout(repo, None)
    assert status(clean, "served tree clean") == "PASS"

    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    dirty = VERIFY.check_checkout(repo, None)
    assert status(dirty, "served tree clean") == "FAIL"


def test_an_expected_commit_that_does_not_match_is_a_failure(tmp_path):
    repo = tmp_path / "served"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    results = VERIFY.check_checkout(repo, "deadbeef")
    assert status(results, "served commit is the expected one") == "FAIL"


def test_a_directory_that_is_not_a_checkout_is_reported(tmp_path):
    results = VERIFY.check_checkout(tmp_path / "nothing", None)
    assert results[0]["status"] == "FAIL"


def test_http_health_reports_an_unreachable_service():
    results = VERIFY.check_http("http://127.0.0.1:9", timeout=0.5)
    assert results[0]["status"] == "FAIL"
    assert "http health" in results[0]["check"]


def test_the_exit_status_is_the_number_of_failures(tmp_path, capsys):
    root = build(tmp_path, rows=10)
    code = VERIFY.main(["--data-root", str(root), "--served-dir", str(tmp_path / "missing"),
                        "--allowlist", "auto"])
    assert code >= 1
    assert "checks passed" in capsys.readouterr().out


@pytest.mark.parametrize("check_name", ["artifact directory", "manifest"])
def test_a_missing_data_root_stops_early(tmp_path, check_name):
    results = VERIFY.run(type("Args", (), {"data_root": tmp_path / "nope", "served_dir": None,
                                           "url": None, "expected_commit": None})())
    assert results[0]["check"] == "artifact directory"
    assert results[0]["status"] == "FAIL"


def test_a_stage_that_only_reports_not_exported_counts_as_zero():
    """The checkpoint dialect counts outcomes; 'not_exported: 500' is a missing stage, not 500 records."""
    manifest = VERIFY.normalise_manifest({
        "countries": {
            "finland": {"exported_videos": 500,
                        "stages": {"8": {"ok": 472, "error": 1, "not_exported": 27},
                                   "9": {"not_exported": 500}}},
        }
    })
    coverage = manifest["stage_coverage"]["finland"]
    assert coverage["8"]["records"] == 472, "only produced outputs count"
    assert coverage["9"]["records"] == 0, "a stage with no outputs must not look complete"


def test_the_checkpoint_dialect_normalises_into_the_artifact_shape():
    manifest = VERIFY.normalise_manifest({
        "countries": {"finland": {"exported_videos": 500}, "poland": {"exported_videos": 500},
                      "portugal": {"exported_videos": 500}},
        "producer_revision": "monday500_20261031",
    })
    assert manifest["records"] == 1500
    assert manifest["record_counts"]["exported_total"] == 1500


def test_a_deployment_without_a_roster_is_still_verifiable(tmp_path):
    """Cohort bookkeeping is optional (Tomi, 2026-11-16): the export is shown as measured."""
    root = build(tmp_path)
    manifest, results = VERIFY.check_manifest(root)
    results += VERIFY.check_artifacts(root, manifest)
    assert [item for item in results if item["status"] == "FAIL"] == []

def test_auto_allowlist_falls_back_to_the_display_list_and_says_so(tmp_path):
    """Two apps, two allowlists: the verifier must name which one it applied."""
    root = build(tmp_path, columns=["country", "video_id", "asr_transcript"])
    manifest, _ = VERIFY.check_manifest(root)
    results = VERIFY.check_artifacts(root, manifest)
    entry = next(item for item in results if item["check"] == "column allowlist")
    assert entry["status"] == "PASS"
    assert "display allowlist" in entry["detail"]
