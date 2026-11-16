"""The deployment questions are answered by functions, so they can be asserted (#258).

The tool exists because "the service is active and the port answers 200" was mistaken for "the change is
live" four times (#176, #185, #234, and the :8502 checkout that ran three commits behind main). Each of those
was a check that was never written. These tests are that check, run against fixtures instead of a host.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))

from served_state import (  # noqa: E402
    Check,
    checkout_drift,
    data_snapshot,
    health,
    render,
    unit_state,
)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def repos(tmp_path: Path) -> dict[str, Path]:
    """A bare origin, a work clone that pushes to it, and a serving clone of it."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "config", "user.email", "test@example.org")
    git(work, "config", "user.name", "Test")
    (work / "app.py").write_text("print('v1')\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "v1")
    git(work, "branch", "-q", "-M", "main")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "-u", "origin", "main")
    # A bare repository does not point HEAD at `main` by itself, and a clone of it would then have
    # no branch checked out -- which is how this fixture first failed.
    subprocess.run(["git", "-C", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)

    serving = tmp_path / "serving"
    subprocess.run(["git", "clone", "-q", str(origin), str(serving)], check=True)
    return {"origin": origin, "work": work, "serving": serving}


def test_a_checkout_equal_to_origin_is_ok(repos: dict[str, Path]):
    result = checkout_drift(repos["serving"], fetch=False)
    assert result.ok, result.problems
    assert "main at" in result.detail


def test_a_checkout_behind_origin_is_reported_with_counts(repos: dict[str, Path], tmp_path: Path):
    """The :8502 defect: healthy service, stale code. It must fail, and say how stale."""
    work = repos["work"]
    (work / "app.py").write_text("print('v2')\n")
    git(work, "commit", "-qam", "v2")
    git(work, "push", "-q", "origin", "main")

    # The serving clone was taken before that push, so it is now one commit behind -- but only once
    # its remote refs have been updated. Fetching without moving HEAD is exactly the served state.
    git(repos["serving"], "fetch", "-q", "origin")
    result = checkout_drift(repos["serving"], fetch=False)
    assert not result.ok
    assert any("1 behind" in problem for problem in result.problems), result.problems


def test_drift_is_invisible_without_a_fetch(repos: dict[str, Path]):
    """A drift check is only as good as the fetch: a stale `origin/main` ref hides a stale deployment."""
    work = repos["work"]
    (work / "app.py").write_text("print('v3')\n")
    git(work, "commit", "-qam", "v3")
    git(work, "push", "-q", "origin", "main")

    blind = checkout_drift(repos["serving"], fetch=False)
    assert blind.ok, "without a fetch the stale remote ref makes a behind checkout look current"

    aware = checkout_drift(repos["serving"], fetch=True)
    assert not aware.ok
    assert any("1 behind" in problem for problem in aware.problems)


def test_a_checkout_on_another_branch_fails(repos: dict[str, Path]):
    git(repos["serving"], "switch", "-q", "-c", "feature")
    result = checkout_drift(repos["serving"], fetch=False)
    assert not result.ok
    assert any("branch" in problem for problem in result.problems)


def test_a_directory_that_is_not_a_checkout_fails(tmp_path: Path):
    result = checkout_drift(tmp_path, fetch=False)
    assert not result.ok
    assert "not a git checkout" in result.detail


def test_a_snapshot_without_a_manifest_is_not_a_snapshot(tmp_path: Path):
    (tmp_path / "combined.csv").write_text("a,b\n")
    result = data_snapshot(tmp_path)
    assert not result.ok
    assert any("manifest" in problem for problem in result.problems)


def test_a_snapshot_reports_its_run_and_rows(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(json.dumps({"run_id": "fiplpt_500", "exported_rows": 1500}))
    result = data_snapshot(tmp_path)
    assert result.ok
    assert "fiplpt_500" in result.detail
    assert "1500" in result.detail


def test_a_manifest_that_declares_per_country_counts_reports_them(tmp_path: Path):
    """The EP24 export declares its size per country, not as one total; a total must not hide a gap."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "version": "ep24-final-export-v1",
        "producer_revision": "monday500_20261031",
        "countries": {
            "finland": {"exported_videos": 500, "input_rows": 900},
            "poland": {"exported_videos": 500, "input_rows": 1100},
            "portugal": {"exported_videos": 500, "input_rows": 800},
        },
    }))
    result = data_snapshot(tmp_path)
    assert result.ok
    assert "monday500_20261031" in result.detail
    assert "videos=1500 over 3 countries" in result.detail


def test_a_missing_data_directory_is_reported_not_raised(tmp_path: Path):
    result = data_snapshot(tmp_path / "absent")
    assert not result.ok
    assert "missing" in result.detail


def test_health_of_a_port_nothing_serves_fails():
    result = health(1, timeout=0.2)
    assert not result.ok
    assert "no answer" in result.problems[0]


def test_unit_state_skips_cleanly_when_no_unit_is_given():
    result = unit_state(None)
    assert result.ok and "skipped" in result.detail


def test_unit_state_reports_a_password_as_set_without_reading_it(monkeypatch):
    """The gate is a fact about the unit; its value must never reach a report or a log."""
    import served_state

    def fake_run(command, *, timeout=30):
        return subprocess.CompletedProcess(
            command,
            0,
            "ActiveState=active\n"
            "WorkingDirectory=/srv/app\n"
            "Environment=LACLAUGPT_VIS_DEMO_PASSWORD=hunter2 OTHER=1\n",
            "",
        )

    monkeypatch.setattr(served_state, "_run", fake_run)
    result = unit_state("app.service")
    assert result.ok
    assert "password set" in result.detail
    assert "hunter2" not in result.detail


def test_render_says_how_many_checks_passed():
    text = render([Check("a", True, "fine"), Check("b", False, "broken", ["why"])])
    assert "[ok  ] a" in text
    assert "[FAIL] b" in text
    assert "        - why" in text
    assert "1/2 checks ok" in text
