"""The contract-check tool must refuse an interpreter older than the declared floor.

Regression guard for #186. Run under Laskin's *system* Python (3.10.12), the tool
used to die with a bare ``ImportError: cannot import name 'StrEnum' from 'enum'``
raised from ``laclaugpt_visualization/plugins.py``, which reads like a contract
violation and exits 1 — the same status a genuine contract failure uses. The tool
must instead name the interpreter floor, the running interpreter and the remedy,
on a status distinct from a failed check.

Same defect class as the Analysis module's #335 and Data-Collection's #315.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPOSITORY_ROOT / "tools" / "verify_contracts.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_contracts_tool", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    return _load_tool()


def test_the_tool_declares_the_same_floor_as_pyproject(tool: ModuleType) -> None:
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    wanted = ".".join(str(part) for part in tool.MINIMUM_PYTHON)
    assert f'requires-python = ">={wanted}"' in pyproject


def test_this_interpreter_is_supported(tool: ModuleType) -> None:
    # The suite runs in the repository virtualenv, so the guard is silent here;
    # if that ever stops being true, this is the canary.
    assert sys.version_info >= tool.MINIMUM_PYTHON
    assert tool.check_interpreter() is None


def test_old_interpreter_gets_an_actionable_message(tool: ModuleType) -> None:
    message = tool.check_interpreter(minimum=(99, 0))
    assert message is not None
    # It must name the requirement, the actual interpreter, and the remedy.
    assert "Python >= 99.0" in message
    assert "requires-python" in message
    assert "enum.StrEnum" in message
    assert ".venv/bin/python tools/verify_contracts.py" in message
    assert sys.executable in message


def test_main_aborts_on_a_distinct_status_for_an_old_interpreter(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tool, "check_interpreter", lambda *a, **k: "interpreter too old")
    # The fixture is read at the top of main(), before any check: if the guard ever
    # moves below it, this fails instead of the tool quietly opening research data
    # on an interpreter it does not support.
    monkeypatch.setattr(tool, "_load_fixture", lambda path: pytest.fail("fixture was loaded"))
    status = tool.main([])
    out = capsys.readouterr().out
    assert status == tool.INTERPRETER_EXIT_STATUS == 2
    assert "ERROR interpreter: interpreter too old" in out
    # It must abort before the import that produces the misleading traceback,
    # i.e. before any check runs.
    assert "all Visualization contract checks passed" not in out
    assert "ok    " not in out
