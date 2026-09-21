"""Regression tests for the dashboard entry point."""

import importlib


def test_dashboard_entry_point_imports() -> None:
    app = importlib.import_module("laclaugpt_visualization.app")
    assert callable(app._load_default_frame)
