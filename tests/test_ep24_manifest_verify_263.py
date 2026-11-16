"""Acceptance 4 of #263: the dashboard reads one layout and the manifest proves it.

The claim under test is "this directory is the export we think it is". Each test is one way that claim can
be false while the app still starts and renders a plausible page.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from laclaugpt_visualization.ep24_manifest_verify import (
    LAYOUT_AMBIGUOUS,
    LAYOUT_FLAT,
    LAYOUT_PER_COUNTRY,
    detect_layout,
    verify_manifest,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        # Explicit LF: the default CRLF would make every byte count disagree with a file rewritten by hand.
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export(root: Path, *, layout: str = LAYOUT_PER_COUNTRY) -> Path:
    """A tiny per-country export with a manifest that describes it — the verified happy path."""
    if layout == LAYOUT_PER_COUNTRY:
        for country in ("finland", "poland", "portugal"):
            _write_csv(root / country / f"{country}.csv",
                       [{"source_key": f"{country}-1", "text": "one"},
                        {"source_key": f"{country}-2", "text": "two"}])
        files = [f"{country}/{country}.csv" for country in ("finland", "poland", "portugal")]
    else:
        _write_csv(root / "combined.csv", [{"source_key": "k1", "text": "one"}])
        files = ["combined.csv"]
    manifest = {
        "layout": layout,
        "file_count": len(files),
        "files": {
            name: {"bytes": (root / name).stat().st_size,
                   "rows": 2 if layout == LAYOUT_PER_COUNTRY else 1,
                   "sha256": _sha256(root / name)}
            for name in files
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_a_matching_directory_is_verified(tmp_path):
    verdict = verify_manifest(_export(tmp_path))
    assert verdict.verdict == "verified"
    assert verdict.files_verified == verdict.files_declared == 3
    assert verdict.layout_declared == verdict.layout_detected == LAYOUT_PER_COUNTRY
    assert verdict.rows_verified == 6
    assert verdict.summary().startswith("3/3 declared files verified")


def test_changed_content_is_a_hash_mismatch_even_when_rows_and_size_agree(tmp_path):
    root = _export(tmp_path, layout=LAYOUT_FLAT)
    path = root / "combined.csv"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"one", b"two"))
    verdict = verify_manifest(root)
    # Same length, same row count, different bytes: only the hash can tell.
    assert path.stat().st_size == len(original)
    assert verdict.verdict == "unverified"
    assert [result.status for result in verdict.mismatched] == ["hash mismatch"]


def test_a_deleted_row_is_reported_as_a_row_count_mismatch_and_named(tmp_path):
    root = _export(tmp_path, layout=LAYOUT_PER_COUNTRY)
    path = root / "finland" / "finland.csv"
    lines = path.read_bytes().split(b"\n")
    declared = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["files"]["finland/finland.csv"]
    # Header only, padded to the declared size so the size check cannot be what catches it.
    path.write_bytes(lines[0] + b" " * max(0, declared["bytes"] - len(lines[0]) - 1) + b"\n")
    verdict = verify_manifest(root)
    finland = next(result for result in verdict.results if result.path == "finland/finland.csv")
    assert finland.status == "row count mismatch"
    assert "declared 2 rows, parsed 0" in finland.detail
    assert verdict.verdict == "unverified"


def test_quoted_newlines_do_not_inflate_the_row_count(tmp_path):
    root = tmp_path
    _write_csv(root / "combined.csv", [{"source_key": "k1", "text": "line one\nline two\nline three"},
                                       {"source_key": "k2", "text": "single"}])
    manifest = {"layout": LAYOUT_FLAT,
                "files": {"combined.csv": {"bytes": (root / "combined.csv").stat().st_size,
                                           "rows": 2,
                                           "sha256": _sha256(root / "combined.csv")}}}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(root).verdict == "verified"


def test_a_missing_declared_file_fails_the_verdict(tmp_path):
    root = _export(tmp_path)
    (root / "poland" / "poland.csv").unlink()
    verdict = verify_manifest(root)
    assert next(result for result in verdict.results if result.path == "poland/poland.csv").status == "missing"
    assert verdict.verdict == "unverified"


def test_undeclared_sidecars_are_listed_but_do_not_fail_a_verified_export(tmp_path):
    root = _export(tmp_path)
    (root / "dictionary.json").write_text("{}", encoding="utf-8")
    verdict = verify_manifest(root)
    assert verdict.verdict == "verified"
    assert "dictionary.json" in verdict.undeclared
    assert "1 undeclared file" in verdict.summary()


def test_a_manifest_for_the_other_layout_is_a_layout_mismatch(tmp_path):
    root = _export(tmp_path, layout=LAYOUT_PER_COUNTRY)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["layout"] = LAYOUT_FLAT
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_manifest(root)
    assert verdict.layout_detected == LAYOUT_PER_COUNTRY
    assert verdict.verdict == "layout mismatch"


def test_two_layouts_in_one_directory_is_ambiguous_not_verified(tmp_path):
    root = _export(tmp_path, layout=LAYOUT_PER_COUNTRY)
    _write_csv(root / "combined.csv", [{"source_key": "k1", "text": "one"}])
    verdict = verify_manifest(root)
    assert verdict.layout_detected == LAYOUT_AMBIGUOUS
    assert verdict.verdict == "layout ambiguous"


def test_no_manifest_is_its_own_verdict(tmp_path):
    _write_csv(tmp_path / "combined.csv", [{"source_key": "k1", "text": "one"}])
    verdict = verify_manifest(tmp_path)
    assert verdict.verdict == "no manifest"
    assert verdict.files_declared == 0
    assert "cannot be verified" in verdict.summary()


def test_an_unreadable_manifest_is_not_a_pass(tmp_path):
    _write_csv(tmp_path / "combined.csv", [{"source_key": "k1", "text": "one"}])
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert verify_manifest(tmp_path).verdict == "no manifest"


def test_detect_layout_names_what_the_directory_holds(tmp_path):
    assert detect_layout(tmp_path) == "absent"
    _export(tmp_path)
    assert detect_layout(tmp_path) == LAYOUT_PER_COUNTRY


def test_hash_limit_skips_hashes_but_still_checks_size_and_rows(tmp_path):
    root = _export(tmp_path)
    path = root / "poland" / "poland.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("one", "ONE"), encoding="utf-8")
    # Nothing is hashed, so the changed bytes are invisible — the limitation is explicit, not silent.
    assert verify_manifest(root, hash_limit=0).verdict == "verified"
    assert verify_manifest(root).verdict == "unverified"
