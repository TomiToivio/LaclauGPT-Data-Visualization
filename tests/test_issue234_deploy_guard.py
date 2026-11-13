"""Regression tests for #234: the deploy guard must see the drift it was blind to.

The live ``:8501`` unit drifted off ``origin/main`` three times (#176, #185, #234) while
``deploy/preflight-laskin-ai26.sh`` stayed green, and a declared core dependency
(``networkx``) was missing from the serving venv without anything noticing. These tests
exercise the guard added for that class in ``deploy/preflight-checkout-ai26.py``.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "deploy" / "preflight-checkout-ai26.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("preflight_checkout_ai26", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd: Path, message: str, *, filename: str = "payload.txt") -> str:
    _git(cwd, "config", "user.email", "guard-test@example.invalid")
    _git(cwd, "config", "user.name", "guard test")
    path = cwd / filename
    path.write_text(path.read_text(encoding="utf-8") + message + "\n" if path.exists() else message + "\n", encoding="utf-8")
    _git(cwd, "add", filename)
    _git(cwd, "commit", "-q", "-m", message)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture()
def served_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A bare ``origin`` with ``main``, plus a clone standing in for the serving checkout."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True
    )
    work = tmp_path / "served"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    _commit(work, "initial")
    _git(work, "push", "-q", "-u", "origin", "HEAD:main")
    return origin, work


def _advance_origin(origin: Path, tmp_path: Path, message: str) -> None:
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _commit(other, message, filename="other.txt")
    _git(other, "push", "-q", "origin", "HEAD:main")


def test_clean_checkout_has_no_problems(served_repo):
    _origin, work = served_repo
    assert guard.checkout_problems(work, fetch=True) == []


def test_checkout_behind_origin_main_is_reported(served_repo, tmp_path):
    origin, work = served_repo
    _advance_origin(origin, tmp_path, "moved on")

    problems = guard.checkout_problems(work, fetch=True)

    assert len(problems) == 1
    assert "0 ahead / 1 behind" in problems[0]


def test_feature_branch_is_reported(served_repo):
    _origin, work = served_repo
    _git(work, "checkout", "-q", "-b", "feat/62-gate-live-steps")
    _commit(work, "branch work", filename="branch.txt")

    problems = guard.checkout_problems(work, fetch=False)

    assert any("not 'main'" in problem for problem in problems)
    assert any("ahead" in problem for problem in problems)


def test_missing_origin_main_is_reported(tmp_path):
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(lonely)], check=True)
    _commit(lonely, "no remote")

    problems = guard.checkout_problems(lonely, fetch=False)

    assert any("origin/main is not available" in problem for problem in problems)


def test_allow_drift_overrides_the_checkout_assertion(served_repo, tmp_path):
    origin, work = served_repo
    _advance_origin(origin, tmp_path, "moved on")

    assert guard.checkout_problems(work, fetch=True, allow_drift=True) == []


def test_missing_core_dependency_is_reported(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["networkx>=3,<4"]\n', encoding="utf-8"
    )

    def missing(name: str) -> str:
        raise ModuleNotFoundError(name)

    problems = guard.dependency_problems(pyproject, version_getter=missing)

    assert problems == [
        "declared core dependency networkx is not installed in the serving venv"
    ]


def test_unsatisfied_version_is_reported(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["networkx>=3,<4"]\n', encoding="utf-8"
    )

    problems = guard.dependency_problems(pyproject, version_getter=lambda _: "2.8.8")

    assert problems == [
        "declared core dependency networkx<4,>=3 is installed as 2.8.8"
    ]


def test_optional_extras_are_not_asserted(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = []\n'
        '[project.optional-dependencies]\nremote = ["pymongo>=4"]\n',
        encoding="utf-8",
    )

    problems = guard.dependency_problems(
        pyproject, version_getter=lambda name: pytest.fail(f"asked for {name}")
    )

    assert problems == []


def test_environment_markers_that_do_not_apply_are_skipped(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\n'
        'dependencies = ["only-on-windows; sys_platform == \'win32\'"]\n',
        encoding="utf-8",
    )

    problems = guard.dependency_problems(
        pyproject, version_getter=lambda name: pytest.fail(f"asked for {name}")
    )

    assert problems == []


def test_the_234_dependency_stays_declared():
    """The guard reads pyproject, so a declared dependency must not silently disappear."""
    declared = guard.declared_dependencies(REPO_ROOT / "pyproject.toml")

    assert any(item.replace(" ", "").startswith("networkx") for item in declared)


def test_this_checkout_satisfies_its_own_core_dependencies():
    """The repository's own environment must pass the dependency half of the guard."""
    assert guard.dependency_problems(REPO_ROOT / "pyproject.toml") == []


def test_main_exits_non_zero_on_drift(served_repo, tmp_path, capsys):
    origin, work = served_repo
    _advance_origin(origin, tmp_path, "moved on")

    exit_code = guard.main(
        ["--repo-root", str(work), "--skip-dependencies", "--pyproject", str(REPO_ROOT / "pyproject.toml")]
    )

    assert exit_code == 1
    assert "behind" in capsys.readouterr().err
