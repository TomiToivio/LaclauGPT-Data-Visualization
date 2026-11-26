"""Browser regression for the bundled D3 component on synthetic data."""
import os
import shutil

import pytest
from test_ai26_networks import artifact, frame

from laclaugpt_visualization.ai26_graph_render import graph_html
from laclaugpt_visualization.ai26_networks import graph_view


def test_offline_force_component():
    api = pytest.importorskip("playwright.sync_api")
    executable = shutil.which("google-chrome") or shutil.which("chromium")
    with api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=executable)
        except api.Error:
            if os.environ.get("GITHUB_ACTIONS"):
                raise
            pytest.skip("Chromium executable unavailable locally")
        try:
            page = browser.new_page(reduced_motion="reduce")
            requests = []
            errors = []
            page.on("request", lambda request: requests.append(request.url))
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(graph_html(graph_view(frame(), artifact())))
            circles = page.locator("circle.node")
            api.expect(circles).to_have_count(3)
            paths = page.locator("path[stroke]")
            api.expect(paths).to_have_count(3)
            assert page.locator("path[stroke][marker-end]").count() == 2
            assert len(set(paths.evaluate_all("items => items.map(item => item.getAttribute('d'))"))) == 3
            circles.first.focus()
            circles.first.press("Enter")
            api.expect(page.locator("#details")).to_contain_text("visible incident edges")
            page.locator("#search").fill("not present")
            assert circles.first.get_attribute("opacity") == "0.16"
            page.locator("#reset").click()
            assert circles.first.get_attribute("opacity") == "1"
            assert not errors
            assert not requests
        finally:
            browser.close()
