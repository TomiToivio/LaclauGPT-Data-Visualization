"""The PLEDGE dashboard ships as a standalone Streamlit script, not as a package module.

It runs from its data directory on the presentation host, so it cannot be imported through
``laclaugpt_visualization``; these tests load it by path, exactly as Streamlit does.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

APP = Path(__file__).resolve().parents[1] / "dashboards" / "pledge"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_pledge_{name}", APP / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_universal_number_search_matches_a_video_id() -> None:
    """A universal number lives in ``video_id``; search once looked at grievances only."""
    import pandas as pd

    search = _load("pledge_search")
    frame = pd.DataFrame({"video_id": ["HEPP24-ES-CR-IG-20240520-1081000"], "grievances": ["housing"]})
    assert search.search_frame(frame, "HEPP24-ES-CR-IG-20240520-1081000", "Universal number").shape[0] == 1


def test_a_query_with_pattern_characters_is_matched_literally() -> None:
    import pandas as pd

    search = _load("pledge_search")
    frame = pd.DataFrame({"video_id": ["v1"], "grievances": ["housing costs (rent + bills)"]})
    assert search.search_frame(frame, "(rent + bills)", "Grievances").shape[0] == 1


def test_same_meaning_entities_merge_and_institutions_do_not() -> None:
    entities = _load("pledge_entities")
    forms = entities.build_forms(
        ["european union"] * 9 + ["eu", "european union eu", "politician", "politicians", "politicians"]
    )
    assert entities.merge_cell("european union eu, politician", forms) == "european union, politicians"
    assert entities.merge_labels(["eu", "european union", "european commission"], forms) == [
        "european union",
        "european commission",
    ]


def test_every_declared_search_scope_names_a_column_the_dashboard_loads() -> None:
    """Guards the two halves drifting: the scopes and REQUIRED_COLUMNS live in different files."""
    source = (APP / "pledge_dashboard.py").read_text(encoding="utf-8")
    search = _load("pledge_search")
    for columns in search.SEARCH_SCOPES.values():
        for column in columns:
            assert f'"{column}"' in source, f"search scope names {column}, dashboard does not load it"
