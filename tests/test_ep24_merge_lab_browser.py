"""Browser acceptance test for the standalone EP24 review and export workflow."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

LAB = Path(__file__).resolve().parents[1] / "scripts/ep24/merge_lab"


def test_drag_resume_and_export(tmp_path):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("Browser acceptance requires Chrome on the CI runner")
        pytest.skip("Chrome is required for browser acceptance")
    (tmp_path / ".git").mkdir()
    source = tmp_path / "analysis/ep24/source/synthetic_dashboard_records.csv"
    source.parent.mkdir(parents=True)
    columns = ["source_url", "entities", "new_entity", "new_theme", "topics", "positive", "neutral", "negative"]
    with source.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        writer.writerow({"source_url": "urn:example:1", "entities": "Council, Council Board"})
        writer.writerow({"source_url": "urn:example:2", "entities": "Council Board"})
    original = source.read_bytes()
    subprocess.run([sys.executable, str(LAB / "lab.py"), str(tmp_path)], check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(LAB / "app.py"),
         "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
         "--browser.gatherUsageStats=false"],
        env={**os.environ, "EP24_PRIVATE_CHECKOUT": str(tmp_path)},
    )
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except urllib.error.URLError:
                time.sleep(0.2)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=chrome)
            page = browser.new_page()
            page.goto(url)
            cards = page.frame_locator("iframe").first.get_by_role("button")
            expect(cards).to_have_count(2, timeout=30000)
            cards.nth(1).drag_to(cards.first)
            expect(page.get_by_text("2 distinct affected records", exact=False)).to_be_visible()
            page.get_by_role("button", name="Confirm merge", exact=True).click()
            expect(page.get_by_text("Revision 2 ·", exact=False)).to_be_visible()
            page.close()
            page = browser.new_page()
            page.goto(url)
            expect(page.get_by_text("Revision 2 ·", exact=False)).to_be_visible(timeout=30000)
            expect(page.frame_locator("iframe").first.get_by_role("button")).to_have_count(1)
            page.get_by_text("I approve this mapping for export", exact=True).click()
            page.get_by_role("button", name="Export approved version").click()
            expect(page.get_by_text("Download manifest.json", exact=True)).to_be_visible()
            browser.close()
        export = tmp_path / "analysis/ep24_legacy_curation/exports/revision-2"
        manifest = json.loads((export / "manifest.json").read_text())
        assert manifest["source_sha256"][source.name] == hashlib.sha256(original).hexdigest()
        assert manifest["record_counts"] == {source.name: 2}
        assert source.read_bytes() == original
        with (export / source.name).open(newline="") as stream:
            records = list(csv.DictReader(stream))
        assert [row["source_url"] for row in records] == ["urn:example:1", "urn:example:2"]
        assert all(row["entities"] == "Council Board" for row in records)
        mapping = json.loads((export / "mapping.json").read_text())
        lineage = {(a["label"], ref) for a in mapping["aliases"].values() for ref in a["refs"]}
        assert lineage == {("Council", "urn:example:1"), ("Council Board", "urn:example:1"),
                           ("Council Board", "urn:example:2")}
        subprocess.run([sys.executable, str(LAB / "import_version.py"), str(tmp_path),
                        "--revision", "2"], check=True)
    finally:
        server.terminate()
        server.wait(timeout=20)
