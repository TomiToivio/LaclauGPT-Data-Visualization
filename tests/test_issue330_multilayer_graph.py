"""Synthetic tests for the combined DA/DNA/SNA graph (#330).

Every test here uses invented labels. The point is the semantics: three layers stay distinguishable,
identity is only ever merged on an approved mapping, and a bounded graph admits that it is bounded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import pytest

from laclaugpt_visualization.graph_api import GraphEnvelope
from laclaugpt_visualization.multilayer import (
    MultilayerFilter,
    build_multilayer,
    ego,
    expand,
    metrics,
    node_key,
    to_envelope,
    write_graphml,
)


def _envelope() -> GraphEnvelope:
    nodes = (
        {
            "id": "a1",
            "label": "Orpo",
            "type": "actor",
            "layer": "laclau",
            "properties": {"platform": "x", "timestamp": "2026-01-10T00:00:00Z"},
        },
        {
            "id": "s1",
            "label": "AI safety",
            "type": "signifier",
            "layer": "laclau",
            "properties": {"empty_signifier": True, "timestamp": "2026-01-10T00:00:00Z"},
        },
        {
            "id": "a1",
            "label": "Orpo",
            "type": "actor",
            "layer": "dna",
            "properties": {"platform": "x"},
        },
        {
            "id": "c1",
            "label": "pacing",
            "type": "concept",
            "layer": "dna",
            "properties": {"platform": "x"},
        },
        {
            "id": "a1",
            "label": "Orpo",
            "type": "actor",
            "layer": "sna",
            "properties": {"platform": "x"},
        },
        {
            "id": "a2",
            "label": "Haavisto",
            "type": "actor",
            "layer": "sna",
            "properties": {"platform": "x"},
        },
    )
    edges = (
        {
            "id": "e-da",
            "source": "s1",
            "target": "a1",
            "type": "articulation",
            "layer": "laclau",
            "weight": 2.0,
            "polarity": "1",
            "timestamp": "2026-01-10T00:00:00Z",
        },
        {
            "id": "e-dna",
            "source": "a1",
            "target": "c1",
            "type": "agrees",
            "layer": "dna",
            "weight": 1.5,
            "polarity": "-1",
        },
        {
            "id": "e-sna",
            "source": "a2",
            "target": "a1",
            "type": "mentions",
            "layer": "sna",
            "weight": 3.0,
            "timestamp": "2026-02-01T00:00:00Z",
        },
    )
    return GraphEnvelope(nodes=nodes, edges=edges, metadata={"study": "AI26"})


def test_three_layers_are_built_and_counted_separately():
    result = build_multilayer(_envelope())
    assert result.layers() == {"da": 2, "dna": 2, "sna": 2}
    assert result.graph.has_node(node_key("da", "signifier", "s1"))
    assert result.graph.has_node(node_key("dna", "concept", "c1"))
    assert result.graph.number_of_edges() == 3


def test_the_same_id_in_two_layers_stays_two_nodes_without_an_identity_mapping():
    """The safety property: a shared identifier is not, by itself, the same actor."""
    result = build_multilayer(_envelope())
    assert result.graph.has_node(node_key("da", "actor", "a1"))
    assert result.graph.has_node(node_key("dna", "actor", "a1"))
    assert result.graph.has_node(node_key("sna", "actor", "a1"))
    assert not any(node.startswith("entity:") for node in result.graph.nodes())


def test_an_approved_identity_mapping_merges_across_layers_and_keeps_every_raw_id():
    result = build_multilayer(_envelope(), identity={"a1": "orpo"})
    assert result.graph.has_node("entity:orpo")
    data = result.graph.nodes["entity:orpo"]
    assert sorted(data["layers"]) == ["da", "dna", "sna"]
    assert data["raw_ids"] == {"da": "a1", "dna": "a1", "sna": "a1"}


def test_edges_keep_direction_type_weight_polarity_and_time():
    result = build_multilayer(_envelope())
    da_edge = result.graph.get_edge_data(node_key("da", "signifier", "s1"), node_key("da", "actor", "a1"))
    payload = next(iter(da_edge.values()))
    assert payload["type"] == "articulation"
    assert payload["weight"] == 2.0
    assert payload["polarity"] == "1"
    assert payload["timestamp"] == datetime(2026, 1, 10, tzinfo=UTC)


def test_filters_compose_and_a_layer_selection_excludes_the_others():
    result = build_multilayer(_envelope(), filter=MultilayerFilter(layers=("dna", "sna")))
    assert result.layers() == {"dna": 2, "sna": 2}
    assert not any("da" in data["layers"] for _, data in result.graph.nodes(data=True))


def test_a_date_window_selects_edges_on_their_own_clock():
    result = build_multilayer(
        _envelope(),
        filter=MultilayerFilter(
            start=datetime(2026, 1, 15, tzinfo=UTC),
            end=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    )
    types = {data["type"] for _, _, data in result.graph.edges(data=True)}
    assert types == {"mentions"}, types


def test_actor_and_empty_signifier_filters_reach_the_nodes_they_name():
    only_empty = build_multilayer(_envelope(), filter=MultilayerFilter(empty_signifiers_only=True))
    assert list(only_empty.graph.nodes()) == [node_key("da", "signifier", "s1")]

    only_haavisto = build_multilayer(_envelope(), filter=MultilayerFilter(actors=("Haavisto",)))
    assert list(only_haavisto.graph.nodes()) == [node_key("sna", "actor", "a2")]


def test_a_filter_that_matches_nothing_returns_an_empty_graph_and_says_why():
    result = build_multilayer(
        _envelope(), filter=MultilayerFilter(actors=("Nobody",), start=datetime(2026, 1, 1))
    )
    assert result.graph.number_of_nodes() == 0
    assert result.disclosure()["nodes"] == 0


def test_minimum_weight_and_edge_type_filters_compose():
    result = build_multilayer(
        _envelope(), filter=MultilayerFilter(min_weight=2.5, edge_types=("mentions", "agrees"))
    )
    assert [data["type"] for _, _, data in result.graph.edges(data=True)] == ["mentions"]


def test_a_capped_graph_records_what_it_dropped_instead_of_pretending():
    result = build_multilayer(_envelope(), max_nodes=2)
    assert result.truncated is True
    assert result.dropped_nodes > 0
    assert any("capped" in note for note in result.notes)
    assert result.disclosure()["truncated"] is True


def test_metrics_are_deterministic_and_describe_the_same_graph_every_time():
    first = build_multilayer(_envelope(), identity={"a1": "orpo"})
    second = build_multilayer(_envelope(), identity={"a1": "orpo"})
    assert metrics(first.graph) == metrics(second.graph)
    stats = metrics(first.graph)
    assert stats["entity:orpo"]["degree"] > 0
    assert all("community" in values for values in stats.values())


def test_envelope_export_round_trips_through_the_same_builder():
    first = build_multilayer(_envelope(), identity={"a1": "orpo"})
    envelope = to_envelope(first)
    assert envelope.metadata["multilayer"] is True
    assert envelope.metadata["disclosure"]["truncated"] is False

    again = build_multilayer(envelope, identity={"a1": "orpo"})
    assert again.graph.number_of_nodes() == first.graph.number_of_nodes()
    assert again.graph.number_of_edges() == first.graph.number_of_edges()


def test_graphml_round_trip_keeps_edge_layers_and_types(tmp_path: Path):
    result = build_multilayer(_envelope())
    path = write_graphml(result, tmp_path / "graph.graphml")
    reloaded = nx.read_graphml(path)
    assert reloaded.number_of_nodes() == result.graph.number_of_nodes()
    edge_layers = {data["layer"] for _, _, data in reloaded.edges(data=True)}
    assert edge_layers == {"da", "dna", "sna"}
    assert {data["edge_type"] for _, _, data in reloaded.edges(data=True)} == {
        "articulation",
        "agrees",
        "mentions",
    }


def test_ego_and_expand_keep_layer_semantics():
    result = build_multilayer(_envelope(), identity={"a1": "orpo"})
    neighbourhood = ego(result, "entity:orpo", radius=1)
    assert neighbourhood.graph.has_node("entity:orpo")
    assert neighbourhood.graph.number_of_nodes() == 4

    only_dna = expand(result, ["entity:orpo"], layer="dna")
    assert only_dna == [node_key("dna", "concept", "c1")]


def test_a_naive_datetime_is_read_as_utc_not_local_time():
    result = build_multilayer(
        _envelope(),
        filter=MultilayerFilter(start=datetime(2026, 2, 1), end=datetime(2026, 2, 1, 23, 59)),
    )
    assert [data["type"] for _, _, data in result.graph.edges(data=True)] == ["mentions"]


@pytest.mark.parametrize("layer", ["laclau", "da", "discourse"])
def test_discourse_layer_names_are_aliases_of_da(layer: str):
    result = build_multilayer(_envelope(), filter=MultilayerFilter(layers=(layer,)))
    assert "da" in result.layers()
