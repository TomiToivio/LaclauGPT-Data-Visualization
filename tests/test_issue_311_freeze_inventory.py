"""The frozen inventory must be able to say "these bytes are not the bytes I reviewed" (#311).

#311 opens by requiring the complete input inventory to be frozen and hashed before any review, because
three independent reviews of a moving corpus measure nothing. A merge-lab run already records a `sha256`
per input and output; `manifest_drift`-style verification is what turns that record into a claim about
*now*.

These tests pin the properties that make the freeze trustworthy, and the one property that keeps it
honest about work not done:

* a file whose bytes still match the run is `verified`, and the document reports itself frozen;
* a file that changed after the run is `changed` — and the document is **not** frozen, even though every
  other file verifies;
* a file the run named that is gone is `missing`, not silently skipped;
* an older manifest with no digest says `unhashed` rather than pretending;
* the review obligation is `labels × 3`, stated beside `reviews_recorded: 0`, so a freeze can never be
  mistaken for a completed review;
* the digest is stable across runs with equal inputs and different for different inputs.

Synthetic fixtures only: temporary directories, no private path or real label appears here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import freeze, sources

PROFILE = """version: 1
sources:
  - name: records
    kind: records
    path: records.csv
    country_column: country
    lists:
      entities: {column: entities, separator: ","}
      themes: {column: political_themes, separator: "\\n"}
      topics: {column: topics, separator: ","}
      sentiment:
        positive: {column: positive, separator: ","}
        neutral: {column: neutral, separator: ","}
        negative: {column: negative, separator: ","}
"""

RECORDS = (
    "country,entities,political_themes,topics,positive,neutral,negative\n"
    'FI,"alpha,beta","cost of living","housing,transport","alpha","",\n'
    'PL,"gamma","rule of law","housing","","gamma",\n'
)


def _run(tmp_path: Path, *, tamper: bool = False, unhashed: bool = False) -> tuple[Path, Path]:
    private = tmp_path / "private"
    (private / "runs" / "R1").mkdir(parents=True)
    (private / "records.csv").write_text(RECORDS, encoding="utf-8")
    (private / "profile.yaml").write_text(PROFILE, encoding="utf-8")

    records = private / "records.csv"
    digest = sources.file_digest(records)
    if tamper:
        records.write_text(RECORDS + 'DE,"delta","","",\n', encoding="utf-8")

    manifest = {
        "run_id": "R1",
        "profile_sha256": sources.file_digest(private / "profile.yaml"),
        "inputs": [
            {
                "source": "records",
                "kind": "records",
                "path": str(records),
                "bytes": len(RECORDS),
                "sha256": "" if unhashed else digest,
            }
        ],
        "outputs": {},
    }
    (private / "runs" / "R1" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return private, private / "runs" / "R1"


def _freeze(private: Path, run_dir: Path, labels=None) -> dict:
    return freeze.freeze(
        profile=sources.load_profile(private / "profile.yaml"),
        profile_path=private / "profile.yaml",
        run_dir=run_dir,
        labels=labels if labels is not None else {"entity": 4, "topic": 3, "sentiment": 2},
    )


class TestVerification:
    def test_unchanged_inputs_are_verified_and_the_document_is_frozen(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        document = _freeze(private, run_dir)
        assert document["inputs"][0]["state"] == "verified"
        assert document["integrity"]["inputs_changed"] == []
        assert document["integrity"]["frozen"] is True

    def test_a_changed_input_is_reported_and_breaks_the_freeze(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path, tamper=True)
        document = _freeze(private, run_dir)
        assert document["inputs"][0]["state"] == "changed"
        assert document["integrity"]["inputs_changed"], "the changed path must be named"
        assert document["integrity"]["frozen"] is False

    def test_a_missing_input_is_missing_not_skipped(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        (private / "records.csv").unlink()
        document = _freeze(private, run_dir)
        assert document["inputs"][0]["state"] == "missing"
        assert document["integrity"]["inputs_missing"] == [str(private / "records.csv")]
        assert document["integrity"]["frozen"] is False

    def test_a_manifest_without_digests_says_unhashed_rather_than_claiming(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path, unhashed=True)
        document = _freeze(private, run_dir)
        assert document["inputs"][0]["state"] == "unhashed"
        assert document["integrity"]["frozen"] is False


class TestWorkload:
    def test_the_obligation_is_three_reviews_per_label_and_none_recorded(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        document = _freeze(private, run_dir)
        workload = document["workload"]
        assert workload["labels_total"] == 9
        assert workload["reviews_required_per_label"] == 3
        assert workload["reviews_required_total"] == 27
        assert workload["reviews_recorded"] == 0, "a freeze may never imply a review happened"

    def test_the_summary_states_both_halves_of_the_ratio(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        summary = freeze.summarize(_freeze(private, run_dir))
        assert "0/27 reviews recorded" in summary
        assert "frozen" in summary

    def test_categories_are_counted_even_when_the_run_wrote_no_tables(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        document = _freeze(private, run_dir)
        assert document["categories"]["entity"]["labels"] == 4
        assert document["categories"]["entity"]["clusters"] == 0


class TestDigest:
    def test_the_same_inputs_give_the_same_digest(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        first = _freeze(private, run_dir)
        second = _freeze(private, run_dir)
        assert first["digest"] == second["digest"]

    def test_different_labels_give_a_different_digest(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        first = _freeze(private, run_dir)
        second = _freeze(private, run_dir, labels={"entity": 5, "topic": 3, "sentiment": 2})
        assert first["digest"] != second["digest"]

    def test_the_written_file_round_trips(self, tmp_path: Path) -> None:
        private, run_dir = _run(tmp_path)
        document = _freeze(private, run_dir)
        target = freeze.write(document, run_dir / "inventory.json")
        assert json.loads(target.read_text(encoding="utf-8"))["digest"] == document["digest"]
