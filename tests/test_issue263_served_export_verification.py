"""The served export is checked against its manifest, so "the data on the host" is a release, not a copy (#263 §3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ep24"))

from verify_served_export import check, main, row_count, sha256_of


def build_export(root: Path) -> Path:
    (root / "finland").mkdir(parents=True)
    (root / "children").mkdir()
    (root / "finland" / "finland.csv").write_text("video_id,country\nA-1,finland\nA-2,finland\n", encoding="utf-8")
    (root / "children" / "themes.csv").write_text("source_key,label\nA,elections\n", encoding="utf-8")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
                "rows": row_count(path),
            }
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"files": {k: {kk: vv for kk, vv in v.items() if vv is not None}
                                              for k, v in files.items()}}), encoding="utf-8")
    return manifest


def test_a_matching_export_reports_nothing(tmp_path: Path):
    manifest = build_export(tmp_path / "export")
    assert check(tmp_path / "export", manifest) == []


def test_a_missing_file_is_named(tmp_path: Path):
    manifest = build_export(tmp_path / "export")
    (tmp_path / "export" / "children" / "themes.csv").unlink()
    problems = check(tmp_path / "export", manifest)
    assert [p["file"] for p in problems] == ["children/themes.csv"]
    assert "missing" in problems[0]["problem"]


def test_a_changed_byte_is_caught_by_the_hash(tmp_path: Path):
    manifest = build_export(tmp_path / "export")
    path = tmp_path / "export" / "finland" / "finland.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("A-2", "A-3"), encoding="utf-8")
    problems = check(tmp_path / "export", manifest)
    assert problems and "sha256" in problems[0]["problem"]


def test_a_same_size_different_content_file_is_still_caught(tmp_path: Path):
    """Size is a cheap first gate, not the check: a rebuild can keep the byte count and change the data."""
    manifest = build_export(tmp_path / "export")
    path = tmp_path / "export" / "finland" / "finland.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("A-1", "A-9"), encoding="utf-8")
    problems = check(tmp_path / "export", manifest)
    assert problems and problems[0]["file"] == "finland/finland.csv"
    assert "sha256" in problems[0]["problem"]


def test_an_undeclared_file_is_reported(tmp_path: Path):
    """This is how a stale flat `combined.csv` survives a layout change and keeps being served."""
    manifest = build_export(tmp_path / "export")
    (tmp_path / "export" / "combined.csv").write_text("video_id\nA-1\n", encoding="utf-8")
    problems = check(tmp_path / "export", manifest)
    assert [p["file"] for p in problems] == ["combined.csv"]
    assert "not declared" in problems[0]["problem"]


def test_a_row_count_mismatch_is_reported(tmp_path: Path):
    payload = json.loads(build_export(tmp_path / "export").read_text(encoding="utf-8"))
    payload["files"]["finland/finland.csv"]["rows"] = 99
    manifest = tmp_path / "export" / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    problems = check(tmp_path / "export", manifest)
    assert any("rows" in p["problem"] for p in problems)


def test_a_missing_served_directory_is_one_clear_finding(tmp_path: Path):
    manifest = build_export(tmp_path / "export")
    problems = check(tmp_path / "absent", manifest)
    assert len(problems) == 1 and "does not exist" in problems[0]["problem"]


def test_the_cli_exits_non_zero_on_a_disagreement(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    manifest = build_export(tmp_path / "export")
    assert main(["--served", str(tmp_path / "export"), "--manifest", str(manifest)]) == 0
    assert "OK" in capsys.readouterr().out

    (tmp_path / "export" / "finland" / "finland.csv").unlink()
    assert main(["--served", str(tmp_path / "export"), "--manifest", str(manifest)]) == 1
    assert "FAIL" in capsys.readouterr().out
