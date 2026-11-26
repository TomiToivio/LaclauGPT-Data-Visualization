"""Synthetic cross-layer network and UTC-filter regressions for #330."""

from datetime import UTC, datetime

import pandas as pd

from laclaugpt_visualization.ai26_graph_render import graph_html
from laclaugpt_visualization.ai26_networks import (
    filter_coded_records,
    filter_publication_window,
    graph_view,
    load_mongo_artifact,
    period_bounds,
)

SOURCE = "https://example.test/a"


def frame():
    return pd.DataFrame(
        [
            {
                "source_url": SOURCE,
                "source_timestamp": "2026-11-23T12:00:00Z",
                "raw_record": {
                    "analysis": {
                        "entities": [{"entity_id": "a", "label": "Example actor"}],
                        "signifiers": [{"object_id": "c", "label": "Safety"}],
                        "empty_signifier_candidates": [{"object_id": "e", "label": "Freedom"}],
                        "relations": [
                            {
                                "relation_id": "r",
                                "source_ref": "a",
                                "target_ref": "c",
                                "relation_type": "articulation",
                                "evidence_ids": ["ev:1"],
                            }
                        ],
                    }
                },
            }
        ]
    )


def artifact():
    def node(ref, kind, layer, label):
        return {"id": ref, "kind": kind, "layer": layer, "label": label}

    def edge(ref, source, target, layer, kind, url=SOURCE, directed=True, stance=None):
        return {
            "id": ref,
            "source": source,
            "target": target,
            "layer": layer,
            "kind": kind,
            "directed": directed,
            "weight": 2.0 if layer == "sna" else None,
            "assertion_kind": "empirical" if layer == "sna" else "coded",
            "properties": {"qualifier": stance},
            "provenance": {"source_url": url, "evidence_ids": ["ev:2"]},
        }

    return {
        "project_id": "AI26",
        "schema_version": "1.0.0",
        "nodes": [
            node("a", "actor", "dna", "Example actor"),
            node("b", "actor", "sna", "Example actor"),
            node("c", "dna-concept", "dna", "Safety"),
        ],
        "edges": [
            edge("dna1", "a", "c", "dna", "statement", stance="agree"),
            edge("sna1", "a", "b", "sna", "mention", directed=False),
            edge("sna2", "a", "b", "sna", "reply", url="https://example.test/other"),
            edge("sna3", "a", "b", "sna", "reply", url=None),
        ],
    }


def test_combined_graph_shares_explicit_typed_ids_not_labels():
    result = graph_view(frame(), artifact())
    assert result["availability"] == {"da": 1, "dna": 1, "sna": 1}
    assert len(result["nodes"]) == 3  # same display name, two distinct actor IDs
    actor = next(item for item in result["nodes"] if item["id"] == "actor:a")
    assert actor["layers"] == ["da", "dna", "sna"]
    assert actor["degree"] == 3
    dna = next(edge for edge in result["edges"] if edge["layer"] == "dna")
    sna = next(edge for edge in result["edges"] if edge["layer"] == "sna")
    assert dna["stance"] == "agree"
    assert sna["directed"] is False
    assert sna["provenance"]["evidence_ids"] == ["ev:2"]
    assert result["omitted_unlinked_edges"] == 1


def test_layer_filters_and_bounds_are_exact():
    result = graph_view(frame(), artifact(), layers=("dna", "sna"), max_edges=1)
    assert len(result["edges"]) == 1
    assert result["truncated"]
    assert result["matched_edges"] == 2
    assert {node["id"] for node in result["nodes"]} == {
        result["edges"][0]["source"],
        result["edges"][0]["target"],
    }
    assert graph_view(frame(), artifact(), layers=())["edges"] == []
    assert graph_view(frame().iloc[:0], artifact())["edges"] == []
    assert graph_view(frame(), artifact(), min_weight=1)["edges"][0]["layer"] == "sna"


def test_publication_clocks_and_empty_signifier_filter():
    now = datetime(2026, 11, 26, 14, tzinfo=UTC)
    dates = period_bounds("Selected UTC week", selected_start="2026-11-26", now=now)
    assert dates[0].isoformat() == "2026-11-23T00:00:00+00:00"
    assert dates[1].isoformat() == "2026-11-30T00:00:00+00:00"
    assert len(filter_publication_window(frame(), *dates)) == 1
    assert filter_publication_window(frame(), *period_bounds("Last 24 hours", now=now)).empty
    assert len(filter_coded_records(frame(), empty_signifiers=("Freedom",))) == 1
    assert filter_coded_records(frame(), empty_signifiers=("Safety",)).empty
    assert len(filter_coded_records(frame(), actors=("Example actor",))) == 1


def test_html_no_network_dependency_or_script_breakout():
    graph = {"nodes": [{"label": "</script><script>alert(1)</script>"}], "edges": []}
    html = graph_html(graph)
    assert "forceSimulation" in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html
    assert "<script src=" not in html


def test_mixed_timestamp_formats_and_provenance_allowlist():
    rows = pd.DataFrame(
        {
            "source_timestamp": [
                "2026-11-23T12:00:00Z",
                "2026-11-23T13:00:00+01:00",
                "2026-11-23",
            ]
        }
    )
    bounds = period_bounds("Selected UTC day", selected_start="2026-11-23")
    assert len(filter_publication_window(rows, *bounds)) == 3
    payload = artifact()
    payload["edges"][0]["provenance"]["unknown_private_field"] = "not exported"
    result = graph_view(frame(), payload)
    assert "unknown_private_field" not in str(result)


class _Cursor:
    """The pymongo cursor surface ``load_mongo_artifact`` uses: filter, sort, bound."""

    def __init__(self, rows):
        self._rows = rows

    def sort(self, key, direction=1):
        return _Cursor(sorted(self._rows, key=lambda row: row.get(key, ""), reverse=direction < 0))

    def limit(self, count):
        return _Cursor(self._rows[:count])

    def __iter__(self):
        return iter(self._rows)


class _Collection:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, projection=None):
        def matches(row):
            for key, expected in query.items():
                if key == "provenance.source_url":
                    if row.get("provenance", {}).get("source_url") not in expected["$in"]:
                        return False
                elif key == "id":
                    if row.get("id") not in expected["$in"]:
                        return False
                elif row.get(key) != expected:
                    return False
            return True

        return _Cursor([row for row in self._rows if matches(row)])

    def find_one(self, query, projection=None):
        return next(iter(self.find(query)), None)


class _Database:
    def __init__(self, edges, nodes=()):
        self._collections = {
            "kg_meta": _Collection([{"project_id": "ai26", "schema_version": "1.0.0"}]),
            "kg_edges": _Collection(list(edges)),
            "kg_nodes": _Collection(list(nodes)),
        }

    def __getitem__(self, name):
        return self._collections[name]


def _projected_edge(edge_id, source, target, layer):
    return {
        "project_id": "ai26",
        "id": edge_id,
        "source": source,
        "target": target,
        "layer": layer,
        "kind": layer,
        "directed": True,
        "weight": None,
        "properties": {},
        "provenance": {"source_url": SOURCE},
    }


def _nodes_for(edges):
    """The graph store's node documents for these edges, as ``MongoGraphStore.write`` stores them."""
    refs = sorted({ref for edge in edges for ref in (edge["source"], edge["target"])})
    return [
        {
            "project_id": "ai26",
            "id": ref,
            "kind": "actor",
            "layer": "dna",
            "label": ref,
            "properties": {},
            "provenance": {"source_url": SOURCE},
        }
        for ref in refs
    ]


def test_a_bounded_graph_window_does_not_zero_the_smallest_layer():
    """A global id-ordered bound filled by DNA must not report SNA as absent (#579).

    Measured on the live store: 33,213 DNA edges against 127 SNA edges, and the loader's 5,000-edge
    window returned 5,000 DNA, SNA 0 — the dashboard then said "0 SNA available edges" for a graph
    that carries them.
    """
    edges = [
        _projected_edge(f"{index:04d}:actor-statement", f"actor:{index}", f"stmt:{index}", "dna")
        for index in range(30)
    ]
    edges += [
        _projected_edge("sna:mention:0001", "actor:a", "actor:b", "sna"),
        _projected_edge("sna:mention:0002", "actor:a", "actor:c", "sna"),
    ]
    artifact = load_mongo_artifact(_Database(edges, _nodes_for(edges)), {SOURCE}, limit=10)
    loaded = sorted(edge["id"] for edge in artifact["edges"])
    assert artifact["input_truncated"] is True
    assert loaded == sorted(
        [f"{index:04d}:actor-statement" for index in range(10)]
        + ["sna:mention:0001", "sna:mention:0002"]
    )
    view = graph_view(frame(), artifact)
    assert view["availability"]["dna"] == 10
    assert view["availability"]["sna"] == 2


def test_an_untruncated_graph_window_says_it_was_not_truncated():
    edges = [
        _projected_edge("0001:actor-statement", "actor:a", "stmt:1", "dna"),
        _projected_edge("sna:mention:0001", "actor:a", "actor:b", "sna"),
    ]
    artifact = load_mongo_artifact(_Database(edges), {SOURCE}, limit=10)
    assert artifact["input_truncated"] is False
    assert len(artifact["edges"]) == 2
