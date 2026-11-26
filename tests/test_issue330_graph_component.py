"""The D3 multilayer component: payload shaping, and a real browser render (#330).

The browser test boots a tiny Streamlit app that renders the component with a synthetic payload.
That is the only way to know the vendored d3 build loads, the component handshake completes, and
nodes actually appear — a unit test of a dictionary cannot tell you the graph is drawn.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from laclaugpt_visualization.components import payload_from_multilayer, payload_from_projection
from laclaugpt_visualization.graph_api import GraphEnvelope
from laclaugpt_visualization.multilayer import build_multilayer


def _envelope() -> GraphEnvelope:
    nodes = (
        {"id": "a1", "label": "Orpo", "type": "actor", "layer": "laclau", "properties": {}},
        {"id": "s1", "label": "AI safety", "type": "signifier", "layer": "laclau", "properties": {}},
        {"id": "a1", "label": "Orpo", "type": "actor", "layer": "sna", "properties": {}},
        {"id": "a2", "label": "Haavisto", "type": "actor", "layer": "sna", "properties": {}},
    )
    edges = (
        {"id": "e1", "source": "s1", "target": "a1", "type": "articulation", "layer": "laclau"},
        {"id": "e2", "source": "a2", "target": "a1", "type": "mentions", "layer": "sna"},
    )
    return GraphEnvelope(nodes=nodes, edges=edges)


def test_a_built_graph_becomes_a_payload_with_layers_and_degrees():
    result = build_multilayer(_envelope(), identity={"a1": "orpo"})
    payload = payload_from_multilayer(result)
    ids = {node["id"] for node in payload["nodes"]}
    assert "entity:orpo" in ids
    orpo = next(node for node in payload["nodes"] if node["id"] == "entity:orpo")
    assert orpo["layer"] == "bridge"  # it carries DA and SNA
    assert sorted(orpo["layers"]) == ["da", "sna"]
    assert orpo["degree"] == 2


def test_the_payload_drops_edges_whose_endpoints_were_cut_and_says_it_is_truncated():
    result = build_multilayer(_envelope(), identity={"a1": "orpo"})
    payload = payload_from_multilayer(result, max_nodes=1)
    assert len(payload["nodes"]) == 1
    assert payload["edges"] == []
    assert payload["disclosure"]["truncated"] is True


def test_a_canonical_projection_is_labelled_other_never_as_a_discourse_layer():
    payload = payload_from_projection(
        {
            "nodes": [{"id": "urn:1", "label": "record"}, {"id": "urn:2", "label": "record"}],
            "edges": [{"source": "urn:1", "target": "urn:2", "type": "citation"}],
            "truncated": False,
        }
    )
    assert {node["layer"] for node in payload["nodes"]} == {"other"}
    assert payload["edges"][0]["type"] == "citation"


def test_projection_edges_to_missing_nodes_are_never_rendered():
    payload = payload_from_projection(
        {"nodes": [{"id": "urn:1"}], "edges": [{"source": "urn:1", "target": "urn:gone"}]}
    )
    assert payload["edges"] == []


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str, seconds: float = 45.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    raise AssertionError(f"Streamlit did not answer at {url}")


def test_the_component_draws_nodes_in_a_real_browser(tmp_path: Path):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("The graph component needs Chrome on the CI runner")
        pytest.skip("Chrome is required for the browser check")

    app = tmp_path / "app.py"
    app.write_text(
        textwrap.dedent(
            """
            import streamlit as st

            from laclaugpt_visualization.components import payload_from_multilayer, render_graph
            from laclaugpt_visualization.graph_api import GraphEnvelope
            from laclaugpt_visualization.multilayer import build_multilayer

            st.set_page_config(layout="wide")
            envelope = GraphEnvelope(
                nodes=(
                    {"id": "a1", "label": "Orpo", "type": "actor", "layer": "laclau", "properties": {}},
                    {"id": "s1", "label": "AI safety", "type": "signifier", "layer": "laclau", "properties": {}},
                    {"id": "a1", "label": "Orpo", "type": "actor", "layer": "sna", "properties": {}},
                    {"id": "a2", "label": "Haavisto", "type": "actor", "layer": "sna", "properties": {}},
                ),
                edges=(
                    {"id": "e1", "source": "s1", "target": "a1", "type": "articulation", "layer": "laclau"},
                    {"id": "e2", "source": "a2", "target": "a1", "type": "mentions", "layer": "sna"},
                ),
            )
            st.write("graph-app-ready")
            render_graph(payload_from_multilayer(build_multilayer(envelope, identity={"a1": "orpo"})))
            """
        )
    )
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    try:
        _wait(url)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(url, wait_until="networkidle")
            page.get_by_text("graph-app-ready").wait_for(timeout=30_000)

            frame = None
            for _ in range(60):
                for candidate in page.frames:
                    if candidate.locator("svg#canvas").count():
                        frame = candidate
                        break
                if frame:
                    break
                page.wait_for_timeout(500)
            assert frame is not None, "the component iframe never appeared"

            frame.locator("circle").first.wait_for(timeout=20_000)
            assert frame.locator("circle").count() >= 3
            assert frame.locator("line").count() >= 2
            # The disclosure line must reach the researcher, not stay in the Python layer.
            assert "not the full network" not in frame.locator("#note").inner_text()
            frame.locator("#search").fill("Orpo")
            frame.locator("#layer-sna").uncheck()
            page.wait_for_timeout(300)
            assert frame.locator("circle").count() >= 1
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=20)
