"""Portable GraphML serializer for derived visualization graphs."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from ._common import INTERPRETATION_WARNING, normalize_projection


def _text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def to_graphml(projection: Mapping[str, Any]) -> str:
    """Return GraphML preserving evidence/source attributes as string data."""
    nodes, edges = normalize_projection(projection)
    root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    graph = SubElement(root, "graph", id="laclaugpt", edgedefault="directed")
    SubElement(graph, "data", key="descriptive_only").text = "true"
    SubElement(graph, "data", key="interpretation_warning").text = INTERPRETATION_WARNING

    for item in nodes:
        node = SubElement(graph, "node", id=item["id"])
        for key, value in sorted(item.items()):
            if key == "id":
                continue
            SubElement(node, "data", key=key).text = _text(value)

    for index, item in enumerate(edges):
        edge = SubElement(
            graph,
            "edge",
            id=str(item.get("id") or f"e{index}"),
            source=item["source"],
            target=item["target"],
        )
        for key, value in sorted(item.items()):
            if key in {"id", "source", "target"}:
                continue
            SubElement(edge, "data", key=key).text = _text(value)

    return tostring(root, encoding="unicode")
