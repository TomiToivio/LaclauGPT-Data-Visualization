"""Synthetic contract checks for normalized DNA child exports (issue #220)."""
import csv
from laclaugpt_visualization.ep24_reprocessed import read_dna_children


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_children_join_only_exact_matching_country_and_parent(tmp_path):
    write_csv(tmp_path / "data/children/finland_dna_statements.csv", [
        {"_storage_id": "A", "statement_id": "s1", "actor_name_raw": "Actor",
         "concept_label_raw": "Concept", "evidence_quote": "Quoted evidence",
         "extraction_prompt_version": "v1"},
        {"_storage_id": "A", "statement_id": "s1", "actor_name_raw": "Actor",
         "concept_label_raw": "Concept", "evidence_quote": "Quoted evidence",
         "extraction_prompt_version": "v1"},
        {"_storage_id": "missing", "statement_id": "s2", "actor_name_raw": "X",
         "concept_label_raw": "Y", "evidence_quote": "", "extraction_prompt_version": ""},
    ])
    write_csv(tmp_path / "data/children/portugal_dna_statements.csv", [
        {"_storage_id": "A", "statement_id": "p1", "actor_name_raw": "PT",
         "concept_label_raw": "Concept", "evidence_quote": "PT quote",
         "extraction_prompt_version": "v2"},
    ])
    parents = [
        {"country": "finland", "_storage_id": "A", "video_id": "123"},
        {"country": "portugal", "_storage_id": "A", "video_id": "456"},
    ]
    found, counts = read_dna_children(tmp_path, parents)
    assert counts == {"read": 4, "matched": 2, "orphan": 1, "ambiguous": 0, "duplicate": 1}
    assert len(found) == 2
    assert {x["country"] for x in found} == {"finland", "portugal"}
    assert {x["evidence_quote"] for x in found} == {"Quoted evidence", "PT quote"}
    assert len({x["document"] for x in found}) == 2


def test_ambiguous_ingest_id_not_inferred(tmp_path):
    write_csv(tmp_path / "children/finland_dna_statements.csv", [
        {"_storage_id": "duplicated", "statement_id": "one", "evidence_quote": "Evidence"},
    ])
    parents = [
        {"country": "finland", "_storage_id": "duplicated", "video_id": "a"},
        {"country": "finland", "_storage_id": "duplicated", "video_id": "b"},
    ]
    found, counts = read_dna_children(tmp_path, parents)
    assert found == []
    assert counts["ambiguous"] == 1
