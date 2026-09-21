"""Issue #155: the dashboard entry point and its pages must be importable.

`app.py` shipped with literal `\\n` escape sequences in place of real newlines, so the module did
not compile at all — while the suite stayed green, because nothing imported it:

    SyntaxError: unexpected character after line continuation character (app.py, line 511)

`app.py` is the canonical dashboard entry point and the Phase 1 pages import from it, so the whole
dashboard was unstartable behind a passing test suite. CI did not catch it either, because the lint
step only checks files changed by the diff.

These tests make the entry point and the page modules at least *importable*, so a syntax error
cannot hide again. They do not exercise Streamlit rendering (that needs a server); they assert the
modules can be parsed and loaded.
"""
from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "laclaugpt_visualization"
APP = PACKAGE / "app.py"
PAGES = sorted((PACKAGE / "pages").glob("*.py"))


def _all_tracked_python() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    return sorted(
        path
        for path in list((root / "src").rglob("*.py")) + list((root / "tests").rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def test_dashboard_entry_point_compiles() -> None:
    """The regression: this file did not parse."""
    py_compile.compile(str(APP), doraise=True)


def test_dashboard_entry_point_imports() -> None:
    """The pages import from here, so a load failure breaks the dashboard."""
    from laclaugpt_visualization.app import _load_default_frame  # noqa: F401


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_dashboard_pages_compile(page: Path) -> None:
    py_compile.compile(str(page), doraise=True)


def test_every_tracked_python_file_parses() -> None:
    """Whole-tree parse gate.

    CI lints only files changed by the diff, so a file that is never touched can sit on `main`
    unable to parse. This asserts the entire source and test tree compiles, which is the cheap
    gate that would have caught #155 (and #138) immediately.
    """
    failures: list[str] = []
    for path in _all_tracked_python():
        try:
            py_compile.compile(str(path), doraise=True, cfile=None)
        except py_compile.PyCompileError as exc:
            failures.append(f"{path.relative_to(Path(__file__).resolve().parents[1])}: {exc}")
    assert not failures, "files that do not parse:\n" + "\n".join(failures)
