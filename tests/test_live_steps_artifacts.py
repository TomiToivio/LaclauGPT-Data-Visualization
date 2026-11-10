"""The live steps 1–7 builder: every source column accounted for, every defect recorded.

The builder is the only thing between a 1.8 GB producer export and a dashboard, so the contracts
that matter are: a record block parses to the full field width, duplicates collapse deterministically,
every source column is classified with a reason, and the manifest names what was dropped.
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_live_steps_artifacts.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load(BUILDER, "build_live_steps_artifacts")

HEADER = ["_storage_id", "country", "video_id", "allas_filename", "source_type",
          "political_preference", "video_duration_seconds", "asr_transcript", "ocr_1",
          "postprocess_entities", "dna_statements_json", "sna_edges_json", "step_01_status",
          "step_02_status", "step_03_status", "step_04_status", "step_05_status",
          "step_06_status", "step_07_status", "processing_status", "preprocess_status",
          "frame_analysis_status", "vllm_video_status", "summary_quality_status",
          "laclau_status", "dna_status", "frame_analysis_1", "summary_analysis",
          "laclau_structured_json", "vllm_video_analysis", "summary_summary_md", "sna_status", "rag_context_json", "vllm_video_prompt",
          "vllm_video_sha256", "metadata"]


def record(storage: str, video: str, *, transcript: str = "hello", statements: int = 1,
           with_sna: bool = False) -> list[str]:
    payload = {
        "_storage_id": storage, "country": "finland", "video_id": video,
        "allas_filename": f"https://example.invalid/{video}.mp4", "source_type": "Instagram",
        "political_preference": "Centre right", "video_duration_seconds": "90",
        "asr_transcript": transcript, "ocr_1": "text on screen",
        "postprocess_entities": '["Entity A"]',
        "dna_statements_json": json.dumps([{"statement_id": f"s{n}", "actor_name_raw": "Actor"}
                                           for n in range(statements)]),
        "sna_edges_json": json.dumps([{"source": "a", "target": "b", "edge_type": "critique"}])
        if with_sna else "",
        "processing_status": "OK", "preprocess_status": "ok", "frame_analysis_status": "ok",
        "vllm_video_status": "ok", "summary_quality_status": "OK", "laclau_status": "ok",
        "dna_status": "ok", "frame_analysis_1": "frame description",
        "summary_analysis": "summary text", "laclau_structured_json": "{}", "vllm_video_analysis": "video analysis",
        "summary_summary_md": "summary markdown",
        "sna_status": "ok" if with_sna else "",
        "rag_context_json": "{}", "vllm_video_prompt": "prompt text",
        "vllm_video_sha256": "deadbeef", "metadata": "{}",
    }
    payload.update({f"step_0{n}_status": "complete" for n in range(1, 8)})
    return [payload.get(name, "") for name in HEADER]


def write_source(directory: Path, name: str, records: list[list[str]]) -> Path:
    path = directory / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for fields in records:
            writer.writerow(fields)
    return path


class ReaderTests(unittest.TestCase):
    """The stdlib reader is the whole parse: no error-dropping, no sniffer to disagree with."""

    def write(self, directory: str, text: str) -> Path:
        path = Path(directory) / "finland_live_steps_1_7.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_quoted_multi_line_cell_is_one_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, 'video_id,allas_filename,source_type\n'
                                         'v,"multi\nline, with comma",Instagram\n')
            rows = list(builder.records(path))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["video_id"], "v")
        self.assertIn("multi", rows[0]["allas_filename"])

    def test_a_row_that_loses_a_field_is_refused_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "video_id,a,b\nv,1\n")
            with self.assertRaises(ValueError) as context:
                list(builder.records(path))
        self.assertIn("header has 3", str(context.exception))

    def test_reader_agrees_with_a_plain_csv_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "video_id,a\nv1,1\nv2,2\n")
            with path.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), len(list(builder.records(path))))

    def test_a_record_date_comes_from_the_media_id(self):
        self.assertEqual(builder.recording_date("HEPP24-FI-RG-IG-20240604-1048000"), "2024-06-04")
        self.assertEqual(builder.recording_date("no-date-here"), "")


class ClassificationTests(unittest.TestCase):
    def test_every_source_column_has_a_class_and_a_reason(self):
        for column in HEADER:
            kind, reason = builder.classify(column)
            self.assertNotEqual(kind, "unclassified", column)
            self.assertTrue(reason, column)

    def test_intermediate_material_is_dropped_with_a_stated_reason(self):
        for column in ("rag_context_json", "vllm_video_prompt", "vllm_video_sha256", "metadata"):
            kind, reason = builder.classify(column)
            self.assertEqual(kind, "dropped", column)
            self.assertTrue(reason)

    def test_human_readable_output_is_kept(self):
        for column in ("step_01_status", "political_preference"):
            self.assertEqual(builder.classify(column)[0], "index", column)
        for column in ("asr_transcript", "ocr_1"):
            self.assertEqual(builder.classify(column)[0], "text", column)
        self.assertEqual(builder.classify("dna_statements_json")[0], "child")


class BuildTests(unittest.TestCase):
    def build(self, records: list[list[str]]) -> tuple[Path, dict]:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = directory / "src"
        source.mkdir()
        write_source(source, "finland_live_steps_1_7.csv", records)
        for country in ("poland", "portugal"):
            write_source(source, f"{country}_live_steps_1_7.csv",
                         [record(f"monday500:{country}:1", f"{country}-video-1")])
        out = directory / "out"
        builder.main(["--source-dir", str(source), "--out", str(out)])
        return out, json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))

    def test_duplicates_collapse_and_the_completeness_winner_is_kept(self):
        out, manifest = self.build([
            record("monday500:fi:a", "video-1", transcript="thin", statements=0),
            record("monday500:fi:b", "video-1", transcript="rich", statements=2),
            record("monday500:fi:c", "video-2"),
        ])
        rows = list(csv.DictReader((out / "finland.csv").open(encoding="utf-8")))
        self.assertEqual(len(rows), 2)
        self.assertEqual(manifest["record_counts"]["finland"]["duplicate_rows"], 1)
        richest = next(row for row in rows if row["video_id"] == "video-1")
        self.assertEqual(richest["_storage_id"], "monday500:fi:b")
        with gzip.open(out / "finland_text.jsonl.gz", "rt", encoding="utf-8") as handle:
            bundle = [json.loads(line) for line in handle]
        self.assertIn("rich", bundle[0]["asr_transcript"])

    def test_the_artifacts_carry_the_app_contract(self):
        out, manifest = self.build([record("monday500:fi:a", "video-1")])
        self.assertEqual(manifest["record_unit"], "video")
        self.assertEqual(manifest["record_counts"]["exported_total"], 3)
        self.assertIn("stage_coverage", manifest)
        self.assertTrue(all(stage["available"] for stage in
                            manifest["stage_coverage"]["finland"].values()))
        self.assertTrue((out / "combined.csv").is_file())
        self.assertTrue((out / "children" / "finland_dna_statements.csv").is_file())
        self.assertEqual(sorted(manifest["unaccounted_source_columns"].values()), [[], [], []])

    def test_statement_children_join_on_the_parent_storage_id(self):
        out, _ = self.build([record("monday500:fi:storage-1", "video-1", statements=3)])
        rows = list(csv.DictReader((out / "children" / "finland_dna_statements.csv").open(
            encoding="utf-8")))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["_storage_id"] for row in rows}, {"monday500:fi:storage-1"})

    def test_a_sna_edge_marks_the_video_as_networked(self):
        out, _ = self.build([record("monday500:fi:a", "video-1", with_sna=True),
                             record("monday500:fi:b2", "video-2", with_sna=False)])
        rows = {row["video_id"]: row for row in
                csv.DictReader((out / "finland.csv").open(encoding="utf-8"))}
        self.assertEqual(rows["video-1"]["has_sna"], "True")
        self.assertEqual(rows["video-2"]["has_sna"], "False")
        self.assertEqual(rows["video-1"]["pipeline_steps_ok"], "7")

    def test_a_dropped_column_never_reaches_the_index(self):
        out, manifest = self.build([record("monday500:fi:a", "video-1")])
        header = next(csv.reader((out / "finland.csv").open(encoding="utf-8")))
        for column in ("rag_context_json", "vllm_video_prompt", "metadata"):
            self.assertNotIn(column, header)
            self.assertIn(column, manifest["inputs"]["finland"]["dropped_reasons"])

    def test_a_stage_the_source_never_reported_is_unavailable_not_zero(self):
        header = [name for name in HEADER if name != "vllm_video_analysis"]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "src"
            source.mkdir()
            for country in ("finland", "poland", "portugal"):
                row = dict(zip(HEADER, record(f"monday500:{country}:1", f"{country}-video-1")))
                path = source / f"{country}_live_steps_1_7.csv"
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerow(row)
            out = Path(directory) / "out"
            builder.main(["--source-dir", str(source), "--out", str(out)])
            manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["stage_coverage"]["finland"]["3_video"]["available"])
        self.assertIn("3_video", manifest["inputs"]["finland"]["stage_unavailable"])

    def test_an_unclassified_column_stops_the_build(self):
        header = HEADER + ["surprise_new_field"]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "src"
            source.mkdir()
            for country in ("finland", "poland", "portugal"):
                path = source / f"{country}_live_steps_1_7.csv"
                row = ["monday500:x"] + ["1"] * (len(header) - 1)
                path.write_text(",".join(header) + "\n" + ",".join(row) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as context:
                builder.main(["--source-dir", str(source), "--out", str(Path(directory) / "out")])
        self.assertIn("unclassified", str(context.exception))


if __name__ == "__main__":
    unittest.main()
