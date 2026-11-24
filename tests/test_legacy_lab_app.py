"""The Merge Lab page renders and wires its five category tabs (issue #300, deliverable 2).

A headless render is the cheapest honest proof: it runs the real app, including the component
declaration and the curation pass, and fails loudly on any import or argument mistake.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "dashboards" / "legacy_curation" / "app.py"

SOURCE = """persons,entities,topics,themes,sentiments
"Petteri Orpo; PM Orpo; Orpo",Finland,migration,climate policy,positive
"Kaja Kallas; Kallas",Suomi,climate policy,climate policy,good
"""


def test_the_lab_renders_five_category_tabs(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "source.csv").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setenv("LACLAUGPT_LEGACY_DIR", str(tmp_path))

    app = AppTest.from_file(str(APP), default_timeout=90)
    app.run()

    assert not app.exception
    assert len(app.tabs) == 5
    # The rule ran: Orpo folds to the full name, Finland absorbs Suomi.
    assert app.metric[1].value != "0"


def test_the_lab_explains_what_to_do_when_no_source_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_LEGACY_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=90)
    app.run()

    assert not app.exception
    assert any("legacy_curate.py" in str(item.value) for item in app.info)
