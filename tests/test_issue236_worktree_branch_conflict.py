"""Regression tests for #236: two deployments, one branch.

A git branch can be checked out in exactly one worktree. When a second dashboard shares the clone
and claims ``main``, the documented refresh of the ``:8501`` deployment cannot check ``main`` out,
and a routine deploy step can leave the served checkout on a maintenance branch — the drift class of
#176, #185 and #234.

The preflight must therefore say *why* the checkout is not on main, and print the remedy, instead of
reporting a bare "not on main".
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "deploy" / "preflight-checkout-ai26.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("preflight_checkout_ai26_236", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd: Path, message: str) -> str:
    _git(cwd, "config", "user.email", "guard-test@example.invalid")
    _git(cwd, "config", "user.name", "guard test")
    path = cwd / "payload.txt"
    path.write_text(
        (path.read_text(encoding="utf-8") if path.exists() else "") + message + "\n",
        encoding="utf-8",
    )
    _git(cwd, "add", "payload.txt")
    _git(cwd, "commit", "-q", "-m", message)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture()
def repo_with_main_taken(tmp_path: Path) -> tuple[Path, Path]:
    """A clone whose ``main`` is checked out in a *second* worktree, while this one is elsewhere."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    served = tmp_path / "served"
    subprocess.run(["git", "clone", "-q", str(origin), str(served)], check=True)
    _commit(served, "initial")
    _git(served, "push", "-q", "-u", "origin", "HEAD:main")

    # The second deployment takes main...
    _git(served, "checkout", "-q", "-b", "maintenance")
    second = tmp_path / "live-steps"
    subprocess.run(
        ["git", "-C", str(served), "worktree", "add", "-q", str(second), "main"], check=True
    )
    return served, second


def test_the_problem_names_the_worktree_that_holds_main(repo_with_main_taken):
    served, second = repo_with_main_taken

    problems = guard.checkout_problems(served, fetch=False)

    assert len(problems) == 2, problems
    message = "\n".join(problems)
    assert "maintenance" in message
    assert "another worktree" in message
    assert str(second) in message, "the operator must be told which checkout is holding main"


def test_the_problem_prints_safe_remedy(repo_with_main_taken):
    served, _second = repo_with_main_taken
    message = "\n".join(guard.checkout_problems(served, fetch=False))
    assert "distinct branch or detached commit" in message
    assert "--ignore-other-worktrees" not in message


def test_a_plain_branch_mismatch_still_reads_plainly(tmp_path: Path):
    """No second worktree: the message stays short, without worktree advice that does not apply."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    served = tmp_path / "served"
    subprocess.run(["git", "clone", "-q", str(origin), str(served)], check=True)
    _commit(served, "initial")
    _git(served, "push", "-q", "-u", "origin", "HEAD:main")
    _git(served, "checkout", "-q", "-b", "maintenance")

    problems = guard.checkout_problems(served, fetch=False)

    assert len(problems) == 1
    assert "another worktree" not in problems[0]
    assert "not 'main'" in problems[0]


def test_a_clean_checkout_has_no_problems(repo_with_main_taken):
    served, second = repo_with_main_taken
    _git(second, "switch", "-c", "deploy/live-steps")
    _git(served, "switch", "main")
    assert guard.checkout_problems(served, fetch=False) == []
