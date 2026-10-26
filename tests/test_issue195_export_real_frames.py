"""Issue #195 Part 1: `export_streaming.py` must survive the *real* cumulative frames.

The canonical exporter (`export_visualization_data.py`) covers small frames and the synthetic
contract. This suite pins the three properties that only matter on the real corpus, all of which the
streaming variant exists for:

* a cumulative frame repeats one video across runs — the row carrying the most stage output must win;
* the Portuguese rows live in a shared legacy export — one country must be selectable out of it;
* a pre-Roihu frame has none of the reprocessed stages — they must read as *unavailable*, not zero.

Fixtures are synthetic: real research data never enters this repository.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ep24"))

import export_streaming as export

STAGES = ("0_ingest", "1_preprocess", "2_frame", "3_video", "4_summary", "5_postprocess",
          "6_discourse", "7_dna", "8_sna", "9_rdf")


def _write(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _run(tmp_path: Path, *args: str) -> int:
    return export.main([*args, "--output", str(tmp_path / "out")])


def _index(tmp_path: Path, country: str) -> list[dict[str, str]]:
    return list(pd.read_csv(tmp_path / "out" / f"{country}.csv", dtype=str,
                            keep_default_na=False).to_dict("records"))


def test_the_most_complete_row_of_a_repeated_video_wins(tmp_path: Path) -> None:
    """Two runs of one video: the later, fuller one is exported — not the first one seen."""
    source = _write(tmp_path / "finland.csv", [
        {"country": "finland", "video_id": "v1", "allas_filename": "v1.mp4",
         "preprocess_status": "complete", "asr_transcript": "early", "laclau_status": ""},
        {"country": "finland", "video_id": "v1", "allas_filename": "v1.mp4",
         "preprocess_status": "complete", "asr_transcript": "late",
         "laclau_status": "complete", "laclau_summary_md": "full discourse output"},
    ])
    assert _run(tmp_path, "--source", f"finland={source}") == 0

    rows = _index(tmp_path, "finland")
    assert len(rows) == 1
    assert rows[0]["laclau_status"] == "complete", "the fuller run must win"
    manifest = json.loads((tmp_path / "out" / "MANIFEST.json").read_text())
    assert manifest["record_counts"]["finland"]["duplicates"] == 1


def test_a_country_can_be_selected_out_of_a_shared_source(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.csv", [
        {"country": "Portugal", "video_id": "t1", "allas_filename": "t1.mp4",
         "whisper_transcript": "portugues"},
        {"country": "Poland", "video_id": "p1", "allas_filename": "p1.mp4",
         "whisper_transcript": "polski"},
        {"country": "Sweden", "video_id": "s1", "allas_filename": "s1.mp4",
         "whisper_transcript": "svenska"},
    ])
    assert _run(tmp_path, "--source", f"portugal={shared}:legacy",
                "--filter-country", "portugal=Portugal") == 0

    rows = _index(tmp_path, "portugal")
    assert [row["video_id"] for row in rows] == ["t1"]


def test_a_legacy_source_reports_stages_unavailable_not_zero(tmp_path: Path) -> None:
    legacy = _write(tmp_path / "poland.csv", [
        {"country": "poland", "video_id": "p1", "allas_filename": "p1.mp4",
         "whisper_transcript": "polski", "summary_analysis": "legacy summary"},
    ])
    assert _run(tmp_path, "--source", f"poland={legacy}:legacy") == 0

    manifest = json.loads((tmp_path / "out" / "MANIFEST.json").read_text())
    coverage = manifest["stage_coverage"]["poland"]
    assert set(coverage) == set(STAGES)
    assert all(entry["records"] == 0 and entry["available"] is False
               for entry in coverage.values()), "a legacy frame must not look like zero findings"
    assert "legacy" in (tmp_path / "out" / "QA_REPORT.md").read_text().lower()


def test_stage_output_reaches_the_text_bundle(tmp_path: Path) -> None:
    source = _write(tmp_path / "finland.csv", [
        {"country": "finland", "video_id": "v1", "allas_filename": "v1.mp4",
         "preprocess_status": "complete", "asr_transcript": "spoken words",
         "laclau_status": "complete", "laclau_summary_md": "discourse output"},
    ])
    assert _run(tmp_path, "--source", f"finland={source}") == 0

    with gzip.open(tmp_path / "out" / "finland_text.jsonl.gz", "rt", encoding="utf-8") as handle:
        record = json.loads(next(handle))
    assert "spoken words" in json.dumps(record)
    assert "discourse output" in json.dumps(record)


def test_an_unclassified_producer_column_fails_the_build(tmp_path: Path) -> None:
    """A new upstream column must be classified deliberately, never dropped on the floor."""
    source = _write(tmp_path / "finland.csv", [
        {"country": "finland", "video_id": "v1", "allas_filename": "v1.mp4",
         "preprocess_status": "complete", "brand_new_upstream_field": "?"},
    ])
    assert _run(tmp_path, "--source", f"finland={source}") == 2
    assert _run(tmp_path, "--source", f"finland={source}", "--allow-unaccounted") == 0


def test_the_export_is_deterministic_and_leaves_the_source_alone(tmp_path: Path) -> None:
    source = _write(tmp_path / "finland.csv", [
        {"country": "finland", "video_id": "v1", "allas_filename": "v1.mp4",
         "preprocess_status": "complete", "asr_transcript": "a"},
        {"country": "finland", "video_id": "v2", "allas_filename": "v2.mp4",
         "preprocess_status": "complete", "asr_transcript": "b"},
    ])
    before = source.read_bytes()
    assert _run(tmp_path, "--source", f"finland={source}") == 0
    first = (tmp_path / "out" / "finland.csv").read_bytes()
    assert _run(tmp_path, "--source", f"finland={source}") == 0
    assert (tmp_path / "out" / "finland.csv").read_bytes() == first
    assert source.read_bytes() == before, "the export must be read-only on its source"
