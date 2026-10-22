"""Regression coverage for issue #186: Python 3.10 must fail before imports."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "verify_contracts.py"


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_contracts_tool", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_floor_matches_pyproject(tool: ModuleType) -> None:
    wanted = ".".join(map(str, tool.MINIMUM_PYTHON))
    assert f'requires-python = ">={wanted}"' in (ROOT / "pyproject.toml").read_text()


def test_supported_interpreter(tool: ModuleType) -> None:
    assert sys.version_info >= tool.MINIMUM_PYTHON
    assert tool.check_interpreter() is None


def test_old_interpreter_message(tool: ModuleType) -> None:
    message = tool.check_interpreter(minimum=(99, 0))
    assert message is not None
    assert "Python >= 99.0" in message
    assert "requires-python" in message
    assert sys.executable in message
    assert "./.venv/bin/python tools/verify_contracts.py" in message


def test_preflight_aborts_before_contract_loading(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tool, "check_interpreter", lambda: "interpreter too old")
    monkeypatch.setattr(tool, "_load_fixture", lambda path: pytest.fail("loaded fixture"))
    assert tool.main([]) == tool.INTERPRETER_EXIT_STATUS == 2
    assert "ERROR interpreter: interpreter too old" in capsys.readouterr().out
