"""Regression checks for the shared AI26 dashboard's public graph controls."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src/laclaugpt_visualization/ai26_dashboard.py"


def test_ai26_dashboard_has_no_file_upload_widget():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "file_uploader"
        for node in ast.walk(tree)
    )


def test_demo_network_renderer_disables_private_graph_controls():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    demo = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_demo")
    calls = [
        node for node in ast.walk(demo)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_networks"
    ]
    assert calls
    assert all(
        any(k.arg == "public_demo" and isinstance(k.value, ast.Constant) and k.value.value is True
            for k in call.keywords)
        for call in calls
    )
