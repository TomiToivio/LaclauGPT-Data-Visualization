"""Serialize a derived graph projection for Cytoscape.js."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import INTERPRETATION_WARNING, normalize_projection


def to_cytoscape(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Return Cytoscape.js element JSON plus explicit epistemic metadata."""
    nodes, edges = normalize_projection(projection)
    elements = [{"data": dict(node)} for node in nodes]
    elements.extend({"data": dict(edge)} for edge in edges)
    return {
        "schema": "laclaugpt.cytoscape.v1",
        "elements": elements,
        "meta": {
            "descriptive_only": True,
            "interpretation_warning": INTERPRETATION_WARNING,
            "bounded": bool(projection.get("bounded", False)),
            "truncated": bool(projection.get("truncated", False)),
        },
    }
