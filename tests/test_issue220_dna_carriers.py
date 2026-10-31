"""Issue #220: the DNA view must read the export's own carriers, not only the row cell.

The EP24 exporter moves every cell longer than its text threshold out of the lean CSV into
``<country>_text.jsonl.gz`` — keyed by the same ``record_id`` the CSV row carries — so a statement
list longer than 1,000 characters is *absent* from ``combined.csv``. It also writes normalized child
tables whose ``_storage_id`` is the statement's own id, at ingest level, so a reader must report the
orphans it cannot attribute rather than attaching them to a listed video.

These tests pin the carrier order (bundle → children → row cells), the bundle key, and the rule that
a swapped export invalidates the scan cache.

Fixtures are synthetic: real research data never enters this repository.
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_visualization.ep24_reprocessed import (
    dna_evidence,
    read_bundle_field,
    record_key,
)

STATEMENTS = [{"statement_id": "s1", "actor_name_raw": "Alice", "concept_label_raw": "Policy",
               "agreement": "1", "evidence_quote": "I support the policy"}]

ROWS = [
    {"record_id": "video:a", "country": "Finland", "source_type": "tiktok", "_storage_id": "hash-a",
     "video_id": "a", "dna_statement_count": "1", "dna_statements_json": ""},
    {"record_id": "video:b", "country": "Finland", "source_type": "tiktok", "_storage_id": "hash-b",
     "video_id": "b", "dna_statement_count": "0", "dna_statements_json": "[]"},
]


def write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_bundle(path: Path, payloads: list[dict]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for payload in payloads:
            stream.write(json.dumps(payload) + "\n")
    return path


class CarrierTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_row_key_prefers_the_exporters_own_id(self) -> None:
        self.assertEqual(record_key(ROWS[0]), "video:a")
        namespaced = record_key({"country": "Finland", "video_id": "a"})
        self.assertTrue(namespaced.endswith("a") and namespaced != "video:a")

    def test_bundle_recovers_a_cell_the_csv_could_not_hold(self) -> None:
        write_bundle(self.root / "finland_text.jsonl.gz",
                     [{"record_id": "video:a", "dna_statements_json": json.dumps(STATEMENTS)}])
        evidence = dna_evidence(ROWS, self.root)
        self.assertEqual(evidence.source, "text bundle")
        self.assertEqual((evidence.statements, evidence.records), (1, 1))
        self.assertEqual(evidence.items[0]["evidence_quote"], "I support the policy")
        self.assertEqual(evidence.counts, {})

    def test_bundle_does_not_leak_rows_outside_the_selection(self) -> None:
        write_bundle(self.root / "finland_text.jsonl.gz",
                     [{"record_id": "video:a", "dna_statements_json": json.dumps(STATEMENTS)},
                      {"record_id": "video:gone", "dna_statements_json": json.dumps(STATEMENTS)}])
        self.assertEqual(dna_evidence([ROWS[0]], self.root).statements, 1)

    def test_children_are_the_fallback_and_orphans_are_counted(self) -> None:
        write_csv(self.root / "children" / "finland_dna_statements.csv", [
            {"_storage_id": "s1", "statement_id": "s1", "source_record_id": "hash-a",
             "actor_name_raw": "Alice", "concept_label_raw": "Policy"},
            {"_storage_id": "s9", "statement_id": "s9", "source_record_id": "hash-collapsed",
             "actor_name_raw": "Ghost", "concept_label_raw": "Orphan"},
        ])
        evidence = dna_evidence(ROWS, self.root)
        self.assertEqual(evidence.source, "children tables")
        self.assertEqual(evidence.statements, 1)
        self.assertEqual(evidence.counts["orphan"], 1)
        self.assertNotIn("Ghost", json.dumps(list(evidence.items)))

    def test_bundle_wins_over_children(self) -> None:
        write_bundle(self.root / "finland_text.jsonl.gz",
                     [{"record_id": "video:a", "dna_statements_json": json.dumps(STATEMENTS)}])
        write_csv(self.root / "children" / "finland_dna_statements.csv", [
            {"_storage_id": "s1", "statement_id": "s1", "source_record_id": "hash-a"},
        ])
        self.assertEqual(dna_evidence(ROWS, self.root).source, "text bundle")

    def test_row_cell_is_the_last_resort(self) -> None:
        rows = [dict(ROWS[0], dna_statements_json=json.dumps({"statements": STATEMENTS}))]
        evidence = dna_evidence(rows, self.root)
        self.assertEqual((evidence.source, evidence.statements), ("row cells", 1))

    def test_no_carrier_is_an_empty_result_not_an_error(self) -> None:
        evidence = dna_evidence(ROWS, self.root)
        self.assertEqual((evidence.statements, evidence.source), (0, "row cells"))

    def test_swapped_export_invalidates_the_bundle_cache(self) -> None:
        bundle = write_bundle(self.root / "finland_text.jsonl.gz",
                              [{"record_id": "video:a", "dna_statements_json": json.dumps(STATEMENTS)}])
        self.assertEqual(len(read_bundle_field(self.root, "dna_statements_json")["video:a"]), 1)
        write_bundle(bundle, [{"record_id": "video:a",
                               "dna_statements_json": json.dumps(STATEMENTS * 2)}])
        self.assertEqual(len(read_bundle_field(self.root, "dna_statements_json")["video:a"]), 2)


if __name__ == "__main__":
    unittest.main()
