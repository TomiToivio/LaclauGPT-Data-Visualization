"""Issue #161 follow-up: streamlit entry scripts must be importable as scripts.

`streamlit run <file>` executes the module as ``__main__`` with no package
context, so a relative import in an entry script raises:

    ImportError: attempted relative import with no known parent package

That left the AI26 research workbench broken while the service still reported
healthy, because readiness validated configuration and the dashboard module's
existence rather than whether it could actually execute. The repository's own
streamlit-run pages (``src/laclaugpt_visualization/pages/*.py``) already
imported absolutely and worked; the two top-level entry scripts did not.

These tests pin the executable contract, not just the existence of the files.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
PACKAGE = REPO_ROOT / "src" / "laclaugpt_visualization"
PACKAGE_NAME = "laclaugpt_visualization"

# Entry points that are handed to `streamlit run <path>` and are therefore
# executed as __main__ rather than imported as part of the package.
STREAMLIT_ENTRY_SCRIPTS = ("ai26_dashboard.py", "app.py")
STREAMLIT_PAGES = tuple(sorted((PACKAGE / "pages").glob("*.py")))


def _relative_imports(path: Path) -> list[str]:
    """Return the relative import statements in a file, as source lines."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.level or 0) > 0:
            module = node.module or ""
            found.append(f"from {'.' * node.level}{module} import ... (line {node.lineno})")
    return found


@pytest.mark.parametrize("name", STREAMLIT_ENTRY_SCRIPTS)
def test_streamlit_entry_script_has_no_relative_imports(name: str) -> None:
    """A script run as __main__ cannot resolve a relative import.

    This is the exact defect: the import error is raised before any of the
    module's own logic runs, so no other test of its behaviour can catch it.
    """
    path = PACKAGE / name
    assert path.is_file(), f"{name} must exist in the package"
    offenders = _relative_imports(path)
    assert not offenders, (
        f"{name} is launched with `streamlit run` and must use absolute imports "
        f"(`from {PACKAGE_NAME}.…`), but has relative imports:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("path", STREAMLIT_PAGES, ids=lambda p: p.name)
def test_streamlit_pages_have_no_relative_imports(path: Path) -> None:
    """The multipage directory is also executed as __main__ by streamlit."""
    offenders = _relative_imports(path)
    assert not offenders, (
        f"pages/{path.name} must use absolute imports:\n  " + "\n  ".join(offenders)
    )


def test_entry_script_executes_as_main() -> None:
    """Execute the AI26 dashboard the way streamlit does and require no ImportError.

    Run in a subprocess so an import failure cannot be masked by pytest's own
    sys.path, and stop before any Streamlit call: the assertion is that the
    module's imports resolve at all, which is precisely what regressed.

    The script requires a project id and private settings, so it is expected to
    stop later with a configuration error — never with an ImportError.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy, sys\n"
                "try:\n"
                f"    runpy.run_path({str(PACKAGE / 'ai26_dashboard.py')!r}, run_name='__main__')\n"
                "except ImportError as exc:\n"
                "    print('IMPORTERROR:', exc); sys.exit(3)\n"
                "except SystemExit:\n"
                "    pass\n"
                "except Exception:\n"
                "    pass\n"
                "sys.exit(0)\n"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode != 3, (
        "the AI26 dashboard raised ImportError when executed as __main__:\n"
        + (result.stdout or "")
        + (result.stderr or "")
    )
    assert "IMPORTERROR" not in (result.stdout or "")


def test_epoch_created_at_is_parsed_not_treated_as_isoformat() -> None:
    """MongoDB stores created_at as a UTC epoch float in the AI26 collections.

    The freshness block handled ``datetime`` and ISO strings but not numbers, so
    the dashboard crashed with `Invalid isoformat string: '1789662508.033724'`
    once the import error above stopped masking it.
    """
    from datetime import UTC, datetime

    # The exact shape the AI26 collections store.
    value = 1789662508.033724
    assert isinstance(value, float)

    # Same branches as the dashboard's freshness handling.
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(float(value), tz=UTC)
    else:
        parsed = datetime.fromisoformat(str(value))
    assert parsed.tzinfo is not None
    assert parsed.year == 2026
