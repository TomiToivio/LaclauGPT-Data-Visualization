"""The continuous served-drift report must see drift, not just deploy-time intent (#234 option b).

`deploy/preflight-checkout-ai26.py` fails a *deploy* closed (#235). It cannot see the defect class
behind #176, #185, #234 and #236: a deployment that starts correctly and then drifts, while the unit
stays active and the port answers 200. These tests pin the observer:

* it ties the port to the checkout the listening process actually runs from (`/proc/<pid>/cwd`),
  because a healthy port proves nothing about which code answers;
* it reports the served branch/HEAD against `origin/main`, and the ahead/behind counts;
* it fails when a branch — `main` in particular — is claimed by two worktrees (#236), because that is
  what makes the documented `git checkout main` refresh fail;
* it never claims a deployment is fine when it could not inspect it.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "served-drift-report.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("served_drift_report", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drift = _load()


class FakeGit:
    """Minimal stand-in for the module's git runner, keyed by the arguments it is called with."""

    def __init__(self, answers: dict[tuple[str, ...], str]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, root: Path, *args: str) -> Any:
        self.calls.append(args)
        stdout = self.answers.get(args, "")
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=stdout, stderr="")


# ------------------------------------------------------------------ parsing


def test_a_deployment_spec_is_strict():
    deployment = drift.parse_deployment("ai26-dashboard=8501:/mnt/workspace/repo")
    assert (deployment.name, deployment.port, deployment.path, deployment.mode) == (
        "ai26-dashboard",
        8501,
        Path("/mnt/workspace/repo"),
        "branch",
    )
    with pytest.raises(ValueError):
        drift.parse_deployment("8501:/mnt/workspace/repo")
    with pytest.raises(ValueError):
        drift.parse_deployment("live=8503:/mnt/repo@sideways")


def test_a_secondary_deployment_can_be_marked_detached():
    """#236/#237: only the :8501 checkout owns main; the others serve a commit."""
    deployment = drift.parse_deployment("live-steps=8503:/mnt/workspace/VZ-live@detached")
    assert (deployment.mode, deployment.path) == ("detached", Path("/mnt/workspace/VZ-live"))


def test_porcelain_branches_are_normalised_to_short_names():
    text = (
        "worktree /a\nHEAD aaa\nbranch refs/heads/main\n\n"
        "worktree /b\nHEAD bbb\nbranch refs/heads/main\n\n"
        "worktree /c\nHEAD ccc\ndetached\n"
    )
    claims = drift.parse_porcelain(text)
    assert claims == {"main": ["/a", "/b"]}


def test_listeners_are_read_per_port():
    text = (
        "LISTEN 0 2048 100.115.95.109:8501 0.0.0.0:* users:((\"python\",pid=342140,fd=6))\n"
        "LISTEN 0 2048 100.115.95.109:8503 0.0.0.0:* users:((\"python\",pid=3681895,fd=6))\n"
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
    )
    assert drift.parse_listeners(text) == {8501: 342140, 8503: 3681895}


# ------------------------------------------------------------------ evaluation


def evaluate(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "branch": "main",
        "head": "8037597abc",
        "upstream": "8037597abc",
        "ahead": 0,
        "behind": 0,
        "listener_cwd": "/mnt/workspace/repo",
        "serving": True,
    }
    base.update(overrides)
    deployment = drift.Deployment("ai26", 8501, Path("/mnt/workspace/repo"))
    return drift.evaluate(deployment, **base)


def test_an_in_sync_deployment_has_no_problems():
    assert evaluate().ok


def test_a_stale_checkout_is_a_problem_with_counts():
    state = evaluate(head="c8f2509fff", ahead=0, behind=2)
    assert not state.ok
    assert "c8f2509" in state.problems[0] and "0 ahead / 2 behind" in state.problems[0]


def test_a_feature_branch_is_a_problem_even_when_up_to_date():
    state = evaluate(branch="feat/62-gate-live-steps", head="f4dc1b1fff")
    assert not state.ok
    assert any("not 'main'" in problem for problem in state.problems)


def test_a_detached_secondary_deployment_is_correct_not_drift():
    state = drift.evaluate(
        drift.Deployment("live-steps", 8503, Path("/mnt/workspace/repo"), mode="detached"),
        branch="HEAD",
        head="8037597abc",
        upstream="8037597abc",
        ahead=0,
        behind=0,
        listener_cwd="/mnt/workspace/repo",
        serving=True,
    )
    assert state.ok


def test_a_secondary_deployment_that_took_a_branch_is_the_layout_defect():
    state = drift.evaluate(
        drift.Deployment("live-steps", 8503, Path("/mnt/workspace/repo"), mode="detached"),
        branch="main",
        head="8037597abc",
        upstream="8037597abc",
        ahead=0,
        behind=0,
        listener_cwd="/mnt/workspace/repo",
        serving=True,
    )
    assert not state.ok
    assert "#236" in state.problems[0]


def test_the_port_must_be_served_by_the_configured_checkout():
    state = evaluate(listener_cwd="/mnt/workspace/VZ-live")
    assert not state.ok
    assert "served from /mnt/workspace/VZ-live" in state.problems[0]


def test_a_silent_port_is_reported_not_passsed():
    state = evaluate(serving=False, listener_cwd="")
    assert not state.ok
    assert "nothing is listening on port 8501" in state.problems[0]


def test_a_duplicate_claim_by_a_deployment_blocks_the_documented_refresh():
    problems, notes = drift.duplicate_branch_problems(
        {"main": ["/a", "/b"], "feat/x": ["/c", "/d"]},
        deployment_paths=[Path("/a"), Path("/b")],
    )
    assert len(problems) == 1
    assert "the documented refresh cannot check out main" in problems[0]
    assert notes == []


def test_a_transient_worktree_holding_main_is_only_a_note():
    """#236's host also carries agent scratch worktrees; they must not fail the guard."""
    problems, notes = drift.duplicate_branch_problems(
        {"main": ["/mnt/repo", "/tmp/v236"]},
        deployment_paths=[Path("/mnt/repo")],
    )
    assert problems == []
    assert len(notes) == 1
    assert "/tmp/v236" in notes[0]


def test_a_single_claim_is_neither():
    assert drift.duplicate_branch_problems({"main": ["/a"]}, deployment_paths=[Path("/a")]) == ([], [])


# ------------------------------------------------------------------ collection (injected IO)


def make_git(head: str, upstream: str, branch: str = "main", behind: int = 0) -> FakeGit:
    return FakeGit(
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): branch + "\n",
            ("rev-parse", "HEAD"): head + "\n",
            ("rev-parse", "--verify", "-q", "origin/main"): upstream + "\n",
            ("rev-list", "--count", f"{upstream}..HEAD"): "0\n",
            ("rev-list", "--count", f"HEAD..{upstream}"): f"{behind}\n",
        }
    )


def test_collect_binds_the_port_to_the_checkout(tmp_path: Path):
    deployment = drift.Deployment("ai26", 8501, tmp_path)
    state = drift.collect(
        deployment,
        listeners=lambda: "LISTEN 0 2048 127.0.0.1:8501 0.0.0.0:* users:((\"python\",pid=42,fd=6))",
        cwd_of=lambda pid: str(tmp_path) if pid == 42 else "",
        git=make_git("aaa", "aaa"),
    )
    assert state.ok
    assert (state.branch, state.head, state.listener_cwd) == ("main", "aaa", str(tmp_path))


def test_collect_reports_a_checkout_that_cannot_tell(tmp_path: Path):
    deployment = drift.Deployment("ai26", 8501, tmp_path)
    git = FakeGit({})  # no origin/main ref at all
    state = drift.collect(deployment, listeners=lambda: "", cwd_of=lambda pid: "", git=git)
    assert not state.ok
    assert "origin/main is not available" in state.problems[0]


def test_collect_reports_a_missing_path(tmp_path: Path):
    deployment = drift.Deployment("ai26", 8501, tmp_path / "gone")
    state = drift.collect(deployment, listeners=lambda: "", cwd_of=lambda pid: "", git=FakeGit({}))
    assert not state.ok
    assert "does not exist" in state.problems[0]


# ------------------------------------------------------------------ end to end on a real repository


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_main_returns_drift_for_a_real_repository(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "config", "user.email", "test@example.com"], check=True)
    subprocess.run([*git, "config", "user.name", "test"], check=True)
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], check=True)
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    # origin/main points at the same commit, but nothing serves the port.
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", head.stdout.strip()], check=True)

    code = drift.main(
        ["--deployment", f"ai26=8501:{repo}", "--skip-worktree-claims", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1  # the port is not served: never silently "ok"
    assert payload["ok"] is False
    assert "nothing is listening on port 8501" in payload["deployments"][0]["problems"][0]
