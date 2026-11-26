"""Offline D3 renderer for the AI26 bounded graph view."""
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def graph_html(graph: dict[str, Any]) -> str:
    """Embed the local pinned D3 bundle. Never load an external script with research data."""
    assets = files("laclaugpt_visualization").joinpath("ai26_graph_assets")
    template = assets.joinpath("force_graph.html").read_text(encoding="utf-8")
    bundle = assets.joinpath("d3.v5.min.js").read_text(encoding="utf-8")
    payload = json.dumps(graph, ensure_ascii=True, default=str).replace("<", "\\u003c")
    # Escaping '<' protects the enclosing script from producer-controlled labels/URLs.
    return template.replace("/* D3_BUNDLE */", bundle).replace("/* GRAPH_DATA */", payload)
