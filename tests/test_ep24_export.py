"""Issue #195 Part 1: the EP24 export contract.

These tests use **synthetic** fixtures only (public Git never holds real research data). They pin the
behaviour the issue's gate depends on:

* one stable row per video, with duplicates counted and unusable ids reported rather than invented;
* every source column classified — an unclassified producer column fails the build;
* one-to-many data becomes normalized child tables, not concatenated cell dumps;
* machine-readable and human-readable stage output both survive;
* a legacy-only source is reported as such instead of pretending the reprocessed stages ran;
* the export never writes into the source directory and never needs a network, a model or a database.
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ep24"))

import export_streaming as export


def write_source(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


REPROCESSED_COLUMNS = [
    "country", "video_id", "_storage_id", "allas_filename", "author_username", "source_type",
    "preprocess_status", "asr_transcript", "ocr_1", "frame_analysis_status", "frame_analysis_1",
    "vllm_video_status", "vllm_video_analysis", "summary_quality_status", "summary_analysis",
    "postprocess_entities", "postprocess_themes", "laclau_status", "laclau_structured_json",
    "laclau_summary_md", "dna_status", "dna_statements_json", "sna_status", "sna_nodes_json",
    "sna_edges_json", "researcher_note", "laclau_raw_response",
]

REPROCESSED_ROWS = [
    {
        "country": "finland", "video_id": "v1", "_storage_id": "s1",
        "allas_filename": "https://a3s.fi/x/v1.mp4", "author_username": "acct",
        "source_type": "tiktok",
        "preprocess_status": "ok", "asr_transcript": "puhutaan populismista",
        "ocr_1": "teksti", "frame_analysis_status": "ok", "frame_analysis_1": "kuvaus",
        "vllm_video_status": "ok", "vllm_video_analysis": "video kertoo",
        "summary_quality_status": "ok", "summary_analysis": "yhteenveto",
        "postprocess_entities": json.dumps([{"label": "Perussuomalaiset", "type": "party"}]),
        "postprocess_themes": json.dumps([{"label": "maahanmuutto"}]),
        "laclau_status": "ok",
        "laclau_structured_json": json.dumps({
            "nodal_points": ["kansa"], "demands": [{"text": "rajat kiinni"}],
            "frontier": "me/he",
        }),
        "laclau_summary_md": "## Analyysi",
        "dna_status": "ok",
        "dna_statements_json": json.dumps([
            {"actor": "Perussuomalaiset", "concept": "maahanmuutto", "stance": "vastustaa",
             "evidence": "rajat kiinni"},
        ]),
        "sna_status": "ok",
        "sna_nodes_json": json.dumps([{"node_id": "n1", "node_type": "actor", "label": "PS"}]),
        "sna_edges_json": json.dumps([{
            "edge_id": "e1", "source": "PS", "target": "Kokoomus", "relation_type": "vastakkain",
            "evidence_quote": "he ovat syyllisiä",
        }]),
        "researcher_note": "tarkista myöhemmin",
        "laclau_raw_response": "RAW MODEL TEXT",
    },
    {
        "country": "finland", "video_id": "v1", "preprocess_status": "ok",   # duplicate key
        "allas_filename": "https://a3s.fi/x/v1.mp4",
    },
    {   # unusable id: no video id, no storage id and no media key — reported, never invented
        "country": "finland", "video_id": "", "_storage_id": "", "allas_filename": "",
    },
]


class ReprocessedExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "source.csv"
        self.output = self.root / "export"
        write_source(self.source, REPROCESSED_ROWS, REPROCESSED_COLUMNS)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _export(self, **kwargs) -> int:
        argv = ["--source", f"finland={self.source}", "--output", str(self.output)]
        for flag, value in kwargs.items():
            argv += [flag, str(value)]
        return export.main(argv)

    def test_one_row_per_video_with_duplicates_and_invalid_ids_counted(self) -> None:
        self.assertEqual(self._export(), 0)
        rows = list(csv.DictReader((self.output / "finland.csv").open(encoding="utf-8")))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["record_key"].startswith("finland/v1#"),
                        "the key carries a disambiguating digest")
        self.assertEqual(rows[0]["has_usable_id"], "1")
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        counts = manifest["record_counts"]["finland"]
        self.assertEqual((counts["read"], counts["exported"], counts["duplicates"],
                          counts["invalid_ids"]), (3, 1, 1, 1))

    def test_producer_output_is_kept_in_both_forms_and_raw_prompts_are_dropped(self) -> None:
        self._export()
        with gzip.open(self.output / "finland_text.jsonl.gz", "rt", encoding="utf-8") as handle:
            record = json.loads(handle.readline())
        self.assertTrue(record["record_key"].startswith("finland/v1#"))
        # human-readable and machine-readable, side by side, in their stage block
        self.assertEqual(record["1_preprocess"]["asr_transcript"], "puhutaan populismista")
        self.assertIn("laclau_structured_json", record["6_discourse"])
        # a backend payload is not exported and is documented as dropped
        self.assertNotIn("laclau_raw_response", json.dumps(record))
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn("laclau_raw_response", manifest["inputs"]["finland"]["dropped_reasons"])

    def test_one_to_many_becomes_normalized_child_tables(self) -> None:
        self._export()
        entities = list(csv.DictReader((self.output / "entities.csv").open(encoding="utf-8")))
        self.assertEqual({row["kind"] for row in entities},
                         {"entity", "theme"})
        self.assertTrue(all(row["record_key"].startswith("finland/v1#") for row in entities))

        claims = list(csv.DictReader((self.output / "discourse_claims.csv").open(encoding="utf-8")))
        self.assertTrue(any(row["kind"] == "discourse:nodal_points" for row in claims))
        self.assertTrue(any(row["label"] == "rajat kiinni" for row in claims))

        dna = list(csv.DictReader((self.output / "dna_statements.csv").open(encoding="utf-8")))
        self.assertEqual(dna[0]["label"], "Perussuomalaiset")
        self.assertEqual(dna[0]["evidence"], "rajat kiinni")

        edges = list(csv.DictReader((self.output / "sna_edges.csv").open(encoding="utf-8")))
        self.assertEqual(edges[0]["evidence"], "he ovat syyllisiä")
        self.assertEqual(edges[0]["role"], "vastakkain")

    def test_index_reports_derived_counts_so_the_dashboard_need_not_parse_json(self) -> None:
        self._export()
        row = next(csv.DictReader((self.output / "finland.csv").open(encoding="utf-8")))
        self.assertEqual(int(row["entity_count"]), 1)
        self.assertEqual(int(row["theme_count"]), 1)
        self.assertEqual(int(row["dna_statement_total"]), 1)
        self.assertEqual(int(row["sna_edge_count"]), 1)
        self.assertIn("5_postprocess=", row["stage_status_summary"])

    def test_unclassified_producer_column_fails_the_build(self) -> None:
        columns = REPROCESSED_COLUMNS + ["brand_new_producer_field"]
        write_source(self.source, [{**REPROCESSED_ROWS[0], "brand_new_producer_field": "x"}], columns)
        self.assertEqual(self._export(), 2)
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["unaccounted_source_columns"]["finland"],
                         ["brand_new_producer_field"])

    def test_coverage_and_qa_name_the_missing_stage(self) -> None:
        self._export()
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn("9_rdf", manifest["inputs"]["finland"]["stage_unavailable"])
        qa = (self.output / "QA_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("unavailable", qa)
        self.assertIn("does **not** validate", qa)

    def test_combined_frame_carries_the_country_namespace(self) -> None:
        self._export()
        rows = list(csv.DictReader((self.output / "combined.csv").open(encoding="utf-8")))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["record_key"].startswith("finland/v1#"))

    def test_mixed_profiles_share_one_combined_header(self) -> None:
        """Finland (reprocessed) and Poland (legacy) must concatenate without losing columns."""
        legacy = self.root / "legacy.csv"
        write_source(legacy, [{"country": "Poland", "video_id": "p1", "summary_analysis": "x"}],
                     ["country", "video_id", "summary_analysis"])
        code = export.main([
            "--source", f"finland={self.source}", "--source", f"poland={legacy}:legacy",
            "--output", str(self.output),
        ])
        self.assertEqual(code, 0)
        with (self.output / "combined.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            header = list(reader.fieldnames or [])
        self.assertEqual(len(rows), 2)
        self.assertIn("laclau_status", header)      # reprocessed-only column survives
        self.assertIn("whisper_transcript", header) or self.assertIn("summary_analysis", header)
        finland = next(r for r in rows if r["country"] == "finland")
        poland = next(r for r in rows if r["country"] == "Poland")
        self.assertTrue(finland["record_key"].startswith("finland/"))
        self.assertTrue(poland["record_key"].startswith("poland/"))

    def test_export_refuses_to_write_into_the_source_directory(self) -> None:
        with self.assertRaises(SystemExit):
            export.main(["--source", f"finland={self.source}", "--output", str(self.root)])


class PrimaryRowSelectionTests(unittest.TestCase):
    """When one video appears repeatedly, the most complete record wins — not the first."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "cumulative.csv"
        self.output = self.root / "export"
        columns = ["country", "video_id", "allas_filename", "preprocess_status",
                   "summary_quality_status", "laclau_status", "dna_status", "summary_analysis",
                   "dna_statements_json"]
        write_source(self.source, [
            {"country": "finland", "video_id": "v", "allas_filename": "m.mp4",
             "summary_quality_status": "ok", "summary_analysis": "early"},
            {"country": "finland", "video_id": "v", "allas_filename": "m.mp4",
             "preprocess_status": "ok", "summary_quality_status": "ok", "laclau_status": "ok",
             "dna_status": "ok", "summary_analysis": "late",
             "dna_statements_json": json.dumps([{"actor": "A", "concept": "B"}])},
        ], columns)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_later_more_complete_row_is_exported(self) -> None:
        self.assertEqual(export.main(["--source", f"finland={self.source}",
                                      "--output", str(self.output)]), 0)
        with gzip.open(self.output / "finland_text.jsonl.gz", "rt", encoding="utf-8") as handle:
            record = json.loads(handle.readline())
        self.assertEqual(record["4_summary"]["summary_analysis"], "late")
        self.assertIn("7_dna", record, "the row that actually ran Step 7 must be the one exported")
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["record_counts"]["finland"]["duplicates"], 1)


class IdentityCollisionTests(unittest.TestCase):
    """The EP24 corpus has up to nine rows sharing one ``video_id``; they must not be merged."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "source.csv"
        self.output = self.root / "export"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_same_video_id_different_segment_is_not_a_duplicate(self) -> None:
        rows = [
            {"country": "finland", "video_id": "vid-x", "source_recording": "rec-a",
             "sequence_number": "1", "source_type": "tiktok", "summary_analysis": "first"},
            {"country": "finland", "video_id": "vid-x", "source_recording": "rec-a",
             "sequence_number": "2", "source_type": "tiktok", "summary_analysis": "second"},
            {"country": "finland", "video_id": "vid-x", "source_recording": "rec-b",
             "sequence_number": "1", "source_type": "tiktok", "summary_analysis": "third"},
        ]
        write_source(self.source, rows, ["country", "video_id", "source_recording",
                                         "sequence_number", "source_type", "summary_analysis"])
        self.assertEqual(export.main(["--source", f"finland={self.source}:legacy",
                                      "--output", str(self.output)]), 0)
        out = list(csv.DictReader((self.output / "finland.csv").open(encoding="utf-8")))
        self.assertEqual(len(out), 3, "three distinct segments, three rows")
        self.assertEqual(len({row["record_key"] for row in out}), 3)
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["record_counts"]["finland"]["duplicates"], 0)


class LegacyProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "legacy.csv"
        self.output = self.root / "export"
        write_source(self.source, [{
            "country": "Poland", "video_id": "p1", "author_username": "acct",
            "whisper_transcript": "transkrypcja", "summary_analysis": "streszczenie",
            "video_file": "/mnt/secret/p1.mp4", "lda_topic": "7",
        }], ["country", "video_id", "author_username", "whisper_transcript", "summary_analysis",
             "video_file", "lda_topic"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_legacy_source_is_labelled_and_every_reprocessed_stage_is_unavailable(self) -> None:
        code = export.main(["--source", f"poland={self.source}:legacy", "--output",
                            str(self.output)])
        self.assertEqual(code, 0)
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["inputs"]["poland"]["profile"], "legacy")
        self.assertEqual(manifest["inputs"]["poland"]["stage_unavailable"],
                         list(export.STAGE_FIELDS))
        qa = (self.output / "QA_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("legacy schema", qa.lower())

    def test_legacy_rows_keep_their_analysis_but_not_host_paths(self) -> None:
        export.main(["--source", f"poland={self.source}:legacy", "--output", str(self.output)])
        row = next(csv.DictReader((self.output / "poland.csv").open(encoding="utf-8")))
        self.assertEqual(row["summary_analysis"], "streszczenie")
        self.assertNotIn("video_file", row)

    def test_a_country_filter_selects_rows_from_a_shared_file(self) -> None:
        shared = self.root / "shared.csv"
        write_source(shared, [
            {"country": "Poland", "video_id": "p1", "summary_analysis": "polski"},
            {"country": "Portugal", "video_id": "pt1", "summary_analysis": "portugues"},
        ], ["country", "video_id", "summary_analysis"])
        code = export.main(["--source", f"portugal={shared}:legacy",
                            "--filter-country", "portugal=Portugal",
                            "--output", str(self.output)])
        self.assertEqual(code, 0)
        rows = list(csv.DictReader((self.output / "portugal.csv").open(encoding="utf-8")))
        self.assertEqual([row["video_id"] for row in rows], ["pt1"])
        self.assertEqual(rows[0]["summary_analysis"], "portugues")


if __name__ == "__main__":
    unittest.main()
