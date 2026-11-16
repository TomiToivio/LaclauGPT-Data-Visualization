"""The checkpoint export's child tables, and the dashboard that reads them (#242).

The delivered export keeps findings in normalised child tables keyed by ``source_key``; the app was
written for the other dialect, where they are JSON columns inside the parent row. These tests pin the
bridge, and pin that the app no longer refuses to render a correct 500-video export because of cohort
bookkeeping (Tomi, 2026-11-16: "make this work with 500 processed videos for each country, ignore the
cohort stuff").
"""
from __future__ import annotations

import csv
from pathlib import Path

from laclaugpt_visualization.ep24_children import (
    by_source,
    coverage,
    load_children,
    network,
    select_children,
    statements,
    term_counts,
)

ROWS = {
    "entities.csv": [
        {"child_id": "1", "source_key": "ep24:finland:x:ig:v1", "country": "finland",
         "field": "postprocess_entities", "index": "0", "origin": "summary",
         "item.label": "European Parliament"},
        {"child_id": "2", "source_key": "ep24:finland:x:ig:v1", "country": "finland",
         "field": "postprocess_entities", "index": "1", "origin": "summary",
         "item.label": "Ilmari Nurminen"},
        {"child_id": "3", "source_key": "ep24:finland:x:ig:v2", "country": "finland",
         "field": "postprocess_entities", "index": "0", "origin": "summary",
         "item.label": "European Parliament"},
    ],
    "themes.csv": [
        {"child_id": "4", "source_key": "ep24:finland:x:ig:v1", "country": "finland",
         "field": "postprocess_themes", "index": "0", "origin": "summary",
         "item.label": "grievance politics"},
    ],
    "dna_statements.csv": [
        {"child_id": "5", "source_key": "ep24:finland:x:ig:v1", "country": "finland",
         "item.actor_id": "a1", "item.actor_name_raw": "Riikka Purra",
         "item.concept_id": "c1", "item.concept_label_raw": "the elite",
         "item.evidence_quote": "they decide for us", "item.confidence": "0.8"},
        {"child_id": "6", "source_key": "ep24:finland:x:ig:v2", "country": "finland",
         "item.actor_name_raw": "Petteri Orpo", "item.concept_label_raw": "the people",
         "item.evidence_quote": "the people deserve better"},
    ],
    "sna_nodes.csv": [
        {"child_id": "7", "source_key": "ep24:finland:x:ig:v1", "item.label": "Riikka Purra",
         "item.kind": "actor"},
    ],
    "sna_edges.csv": [
        {"child_id": "8", "source_key": "ep24:finland:x:ig:v1",
         "item.source_actor": "Riikka Purra", "item.target_actor": "Petteri Orpo",
         "item.edge_type": "critique", "item.evidence_quote": "after rolling back"},
        {"child_id": "9", "source_key": "ep24:finland:x:ig:v2",
         "item.source_actor": "Petteri Orpo", "item.target_actor": "Riikka Purra",
         "item.edge_type": "critique", "item.evidence_quote": ""},
    ],
}


def build(tmp_path: Path) -> Path:
    for filename, rows in ROWS.items():
        with (tmp_path / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return tmp_path


def test_child_tables_are_read_without_the_exporter_prefix(tmp_path):
    children = load_children(build(tmp_path))
    assert children["entities"][0]["label"] == "European Parliament"
    assert "item.label" not in children["entities"][0]
    assert children["dna"][0]["actor_name_raw"] == "Riikka Purra"


def test_term_counts_count_a_video_once_even_when_it_lists_a_term_twice(tmp_path):
    children = load_children(build(tmp_path))
    ranked = term_counts(children["entities"])
    assert ranked[0] == {"Term": "European Parliament", "Videos / mentions": 2}
    assert {"Term": "Ilmari Nurminen", "Videos / mentions": 1} in ranked


def test_children_group_by_the_parent_source_key(tmp_path):
    children = load_children(build(tmp_path))
    grouped = by_source(children["dna"])
    assert set(grouped) == {"ep24:finland:x:ig:v1", "ep24:finland:x:ig:v2"}
    assert grouped["ep24:finland:x:ig:v1"][0]["concept_label_raw"] == "the elite"


def test_dna_statements_are_rendered_with_their_evidence(tmp_path):
    items = statements(load_children(build(tmp_path))["dna"])
    assert items[0]["actor"] == "Riikka Purra"
    assert items[0]["concept"] == "the elite"
    assert items[0]["evidence_quote"] == "they decide for us"


def test_sna_edges_without_a_quotation_are_not_promoted_to_evidence(tmp_path):
    nodes, edges = network(load_children(build(tmp_path))["sna_nodes"],
                           load_children(build(tmp_path))["sna_edges"])
    assert nodes[0]["label"] == "Riikka Purra"
    assert len(edges) == 2, "both rows are returned; the app decides which carry evidence"
    assert edges[0]["relation_type"] == "critique"
    assert edges[0]["document"] == "ep24:finland:x:ig:v1"


def test_coverage_reports_the_denominator_a_view_needs(tmp_path):
    table = coverage(load_children(build(tmp_path)))
    entities = next(row for row in table if row["child table"] == "entities")
    assert entities["rows"] == 3
    assert entities["videos"] == 2


def test_a_missing_child_table_is_empty_not_an_error(tmp_path):
    children = load_children(tmp_path)
    assert children["entities"] == []
    assert term_counts(children["entities"]) == []


def test_filtered_children_never_include_other_countries_or_videos(tmp_path):
    children = load_children(build(tmp_path))
    # Only one FI video is visible after filtering. The second FI video
    # and a Polish one must not contribute to any child-backed chart.
    children["dna"].append({
        "source_key": "ep24:poland:x:ig:v3",
        "actor_name_raw": "Polish actor", "concept_label_raw": "different concept",
    })
    filtered = select_children(children, [{"source_key": "ep24:finland:x:ig:v1"}])
    assert len(filtered["entities"]) == 2
    assert len(filtered["themes"]) == 1
    assert len(filtered["dna"]) == 1
    assert len(filtered["sna_edges"]) == 1
    assert filtered["dna"][0]["actor_name_raw"] == "Riikka Purra"

    # An empty filtered result must not show evidence from the entire export.
    assert all(not items for items in select_children(children, []).values())


def test_filtered_children_do_not_join_by_nonnamespaced_video_id():
    children = {"dna": [
        {"source_key": "ep24:finland:x:ig:123", "video_id": "123"},
        {"source_key": "ep24:poland:x:ig:123", "video_id": "123"},
    ]}
    selected = select_children(children, [
        {"source_key": "ep24:poland:x:ig:123", "video_id": "123"}
    ])
    assert selected["dna"] == [children["dna"][1]]


def test_filtered_children_support_normalized_parent_record_ids():
    children = {"dna": [{"parent_record_id": "fi:one"}, {"parent_record_id": "pl:one"}]}
    selected = select_children(children, [{"record_id": "fi:one"}])
    assert selected["dna"] == [children["dna"][0]]
