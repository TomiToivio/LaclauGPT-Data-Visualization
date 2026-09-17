from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.legacy.art.preprocess import preprocess as preprocess_art
from scripts.legacy.pledge.preprocess import preprocess as preprocess_pledge

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_golden.json"


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_pledge_preserves_alignment_provenance_and_raw_tokens(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["pledge"]
    source = tmp_path / "pledge.csv"
    _write_csv(source, fixture["rows"])
    model = preprocess_pledge(source)
    counts = model["quality"]["alignment_status"]
    assert counts == fixture["expected_alignment_status"]
    assert model["records"][1]["political_alignment_raw"] is None
    assert model["records"][1]["political_alignment"] == "Centre"
    assert model["records"][1]["alignment_observation_status"] == "legacy_derived"
    ai_tokens = [row for row in model["tokens"] if row["canonical_term"] == "ai"]
    assert ai_tokens and all(row["raw_term"] == "AI" for row in ai_tokens)


def test_art_parser_preserves_raw_terms_and_builds_country_edges(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["art"]
    source = tmp_path / "art.csv"
    _write_csv(source, fixture["rows"])
    model = preprocess_art(source)
    assert model["quality"]["parsed_concepts"] == fixture["expected_concepts"]
    assert all("raw_term" in row and "canonical_term" in row for row in model["concepts"])
    public_ai = [edge for edge in model["concept_edges"] if edge["canonical_term"] == "public ai"]
    assert len(public_ai) == fixture["expected_public_ai_edges"]
    assert model["geometry"]["orbital"] == "decorative"
