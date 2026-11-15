#!/usr/bin/env python3
"""Report what the live deployments are actually serving, continuously (#234 option b).

`deploy/preflight-checkout-ai26.py` (#235) fails a *deploy* closed when the checkout has drifted
from ``origin/main`` or a declared core dependency is missing. That guard runs once, at the moment
somebody deploys. The defect it cannot see is the one #176, #185 and #234 all were: a deployment that
started correctly and then **drifted afterwards** — a later ``git checkout`` for unrelated work, a
worktree that took ``main`` away, a ``pull`` that landed on the wrong branch — while the unit stays
``active`` and the port keeps answering 200.

This script is the continuous half. It reads what is being served, not what a deploy intended:

* the checkout the listening process on each port actually runs from
  (``/proc/<pid>/cwd`` compared with the configured path, so "which code answers" is tied to a port);
* that checkout's branch, HEAD, and its ahead/behind relation to ``origin/main``;
* whether any branch is claimed by more than one worktree — the #236 defect, where ``main`` was held
  by both the AI26 and the live-steps worktree and the documented refresh could not check out ``main``.

Read-only: it runs no git command that writes, never restarts anything and never touches data.

Exit codes: ``0`` all deployments serve ``origin/main`` and no branch is multiply claimed, ``1`` at
least one problem, ``2`` a deployment could not be inspected at all (not serving, no git, no ref).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: The Laskin layout, documented in docs/AI26_LASKIN_DASHBOARD.md. Override with --deployment.
#: ``@detached`` marks a secondary deployment: the documented convention (#236/#237) is that the AI26
#: checkout on :8501 owns ``main`` and every additional deployment is a detached worktree, so a
#: detached HEAD is *correct* there rather than drift.
DEFAULT_DEPLOYMENTS: tuple[str, ...] = (
    "ai26-dashboard=8501:/mnt/workspace/LaclauGPT-Data-Visualization",
    "live-steps=8503:/mnt/workspace/VZ-live@detached",
)

UPSTREAM = "origin/main"

MODES = ("branch", "detached")


@dataclass(frozen=True)
class Deployment:
    """One long-running deployment: a name, the port it answers on, and the checkout it serves."""

    name: str
    port: int
    path: Path
    #: ``branch``: this checkout owns ``main``. ``detached``: it must serve a commit, not a branch.
    mode: str = "branch"


@dataclass
class DeploymentState:
    """What was observed for one deployment. Everything is a string so it can be printed."""

    deployment: Deployment
    branch: str = ""
    head: str = ""
    behind: int = 0
    ahead: int = 0
    listener_cwd: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_deployment(spec: str) -> Deployment:
    """``name=port:path[@detached]`` -> Deployment. Strict: a typo must not silently scan nothing."""
    match = re.fullmatch(
        r"(?P<name>[^=]+)=(?P<port>\d+):(?P<path>[^@]+)(?:@(?P<mode>branch|detached))?",
        spec.strip(),
    )
    if not match:
        raise ValueError(f"deployment spec must be name=port:path[@detached], got {spec!r}")
    return Deployment(
        name=match.group("name").strip(),
        port=int(match.group("port")),
        path=Path(match.group("path").strip()),
        mode=match.group("mode") or "branch",
    )


def parse_porcelain(text: str) -> dict[str, list[str]]:
    """``git worktree list --porcelain`` -> branch name -> worktree paths (for duplicate claims)."""
    claims: dict[str, list[str]] = {}
    path = ""
    for line in text.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :].strip()
        elif line.startswith("branch "):
            branch = line[len("branch ") :].strip()
            branch = branch.rsplit("/", 1)[-1] if "refs/heads/" in branch else branch
            claims.setdefault(branch, []).append(path)
    return claims


def parse_listeners(text: str) -> dict[int, int]:
    """``ss -ltnp`` output -> port -> pid, for the ports that name a process."""
    listeners: dict[int, int] = {}
    for line in text.splitlines():
        port_match = re.search(r":(\d+)\s", line)
        pid_match = re.search(r"pid=(\d+)", line)
        if port_match and pid_match:
            listeners[int(port_match.group(1))] = int(pid_match.group(1))
    return listeners


def duplicate_branch_problems(
    claims: dict[str, list[str]],
    *,
    deployment_paths: Sequence[Path] = (),
    branch: str = "main",
) -> tuple[list[str], list[str]]:
    """Split duplicate branch claims into (problems, notes).

    #236: a branch claimed by two *deployments* cannot be checked out by either refresh procedure, so
    that is a problem. A claim held by a transient worktree (an agent's scratch checkout, a review
    checkout under ``/tmp``) is only a note: it does not belong to a deployment and it disappears on
    its own, but a reader still wants to know why ``git checkout main`` refused.
    """
    configured = {path.resolve() for path in deployment_paths}
    problems: list[str] = []
    notes: list[str] = []
    for name, paths in sorted(claims.items()):
        if len(paths) < 2 or name != branch:
            continue
        held = {Path(path).resolve() for path in paths}
        shown = ", ".join(paths)
        # One deployment holding the branch is the documented layout. Two deployments holding it is the
        # #236 defect: exactly one of them can refresh non-interactively.
        if len(held & configured) >= 2:
            problems.append(
                f"branch {branch!r} is checked out in {len(paths)} worktrees ({shown}); "
                "the documented refresh cannot check out main non-interactively"
            )
        elif held - configured:
            notes.append(
                f"branch {branch!r} is also checked out outside the deployments ({shown}); "
                "harmless for the guard, but a manual `git checkout main` will refuse"
            )
    return problems, notes


def evaluate(
    deployment: Deployment,
    *,
    branch: str,
    head: str,
    upstream: str,
    ahead: int,
    behind: int,
    listener_cwd: str,
    serving: bool,
) -> DeploymentState:
    """Turn one deployment's observations into a state with named problems. Pure."""
    state = DeploymentState(
        deployment=deployment,
        branch=branch,
        head=head,
        ahead=ahead,
        behind=behind,
        listener_cwd=listener_cwd,
    )
    if not serving:
        state.problems.append(f"nothing is listening on port {deployment.port}")
        return state
    if Path(listener_cwd).resolve() != deployment.path.resolve():
        state.problems.append(
            f"port {deployment.port} is served from {listener_cwd or '<unknown>'}, "
            f"not the configured {deployment.path}"
        )
    if deployment.mode == "branch":
        if branch != "main":
            state.problems.append(f"serving checkout is on branch {branch!r}, not 'main'")
    elif branch != "HEAD":
        # #236/#237: a secondary deployment must be a detached worktree so it never takes `main` from
        # the checkout that owns it. Finding it on a branch is the layout defect, not a refresh.
        state.problems.append(
            f"secondary deployment is on branch {branch!r}; it must be a detached worktree "
            "so it does not claim a branch (#236)"
        )
    if head != upstream:
        state.problems.append(
            f"serving checkout is {head[:7]}, {UPSTREAM} is {upstream[:7]} "
            f"({ahead} ahead / {behind} behind)"
        )
    return state


# ------------------------------------------------------------------ IO


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def _listeners() -> str:
    return subprocess.run(
        ["ss", "-ltnp"], capture_output=True, text=True, check=False
    ).stdout


def _listener_cwd(pid: int) -> str:
    try:
        return str(Path(f"/proc/{pid}/cwd").resolve())
    except OSError:
        return ""


def collect(
    deployment: Deployment,
    *,
    fetch: bool = False,
    listeners: Callable[[], str] = _listeners,
    cwd_of: Callable[[int], str] = _listener_cwd,
    git: Callable[..., subprocess.CompletedProcess[str]] = _git,
) -> DeploymentState:
    """Observe one deployment. Injectable so the tests need no server, port or repository."""
    if not deployment.path.is_dir():
        return DeploymentState(
            deployment=deployment,
            problems=[f"checkout path does not exist: {deployment.path}"],
        )

    if fetch:
        git(deployment.path, "fetch", "-q", "--prune", "origin")

    branch = git(deployment.path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = git(deployment.path, "rev-parse", "HEAD").stdout.strip()
    upstream_ref = git(deployment.path, "rev-parse", "--verify", "-q", UPSTREAM).stdout.strip()
    if not upstream_ref:
        return DeploymentState(
            deployment=deployment,
            branch=branch,
            head=head,
            problems=[f"{UPSTREAM} is not available in this checkout"],
        )
    ahead = git(deployment.path, "rev-list", "--count", f"{upstream_ref}..HEAD").stdout.strip()
    behind = git(deployment.path, "rev-list", "--count", f"HEAD..{upstream_ref}").stdout.strip()

    port_pid = parse_listeners(listeners()).get(deployment.port)
    return evaluate(
        deployment,
        branch=branch,
        head=head,
        upstream=upstream_ref,
        ahead=int(ahead or 0),
        behind=int(behind or 0),
        listener_cwd=cwd_of(port_pid) if port_pid else "",
        serving=port_pid is not None,
    )


def worktree_claims(path: Path) -> dict[str, list[str]]:
    """Branch -> worktree paths for the repository that ``path`` belongs to."""
    top = _git(path, "rev-parse", "--show-toplevel").stdout.strip()
    if not top:
        return {}
    return parse_porcelain(_git(Path(top), "worktree", "list", "--porcelain").stdout)


def render(
    states: Sequence[DeploymentState],
    claim_problems: Sequence[str],
    claim_notes: Sequence[str] = (),
) -> str:
    lines = []
    for state in states:
        marker = "ok   " if state.ok else "DRIFT"
        position = state.branch if state.deployment.mode == "branch" else f"detached@{(state.head or '?')[:7]}"
        lines.append(
            f"{marker} {state.deployment.name:<16} :{state.deployment.port:<5} "
            f"{position:<20} {(state.head or '?')[:7]:<8} "
            f"{state.ahead} ahead / {state.behind} behind"
        )
        for problem in state.problems:
            lines.append(f"      - {problem}")
    for problem in claim_problems:
        lines.append(f"DRIFT worktree claims  {problem}")
    for note in claim_notes:
        lines.append(f"note  worktree claims  {note}")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report what the live deployments serve, and whether it is origin/main (#234)."
    )
    parser.add_argument(
        "--deployment",
        action="append",
        default=None,
        metavar="NAME=PORT:PATH",
        help=f"deployment to inspect; defaults are {', '.join(DEFAULT_DEPLOYMENTS)}",
    )
    parser.add_argument("--fetch", action="store_true", help="git fetch origin first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--skip-worktree-claims",
        action="store_true",
        help="do not report duplicate branch claims (#236)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    specs = args.deployment or list(DEFAULT_DEPLOYMENTS)
    try:
        deployments = [parse_deployment(spec) for spec in specs]
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    states = [collect(deployment, fetch=args.fetch) for deployment in deployments]
    claim_problems: list[str] = []
    claim_notes: list[str] = []
    if not args.skip_worktree_claims and deployments:
        claim_problems, claim_notes = duplicate_branch_problems(
            worktree_claims(deployments[0].path),
            deployment_paths=[deployment.path for deployment in deployments],
        )

    if args.json:
        print(
            json.dumps(
                {
                    "deployments": [
                        {
                            "name": state.deployment.name,
                            "port": state.deployment.port,
                            "path": str(state.deployment.path),
                            "branch": state.branch,
                            "head": state.head,
                            "ahead": state.ahead,
                            "behind": state.behind,
                            "listener_cwd": state.listener_cwd,
                            "ok": state.ok,
                            "problems": state.problems,
                        }
                        for state in states
                    ],
                    "worktree_claims": claim_problems,
                    "worktree_notes": claim_notes,
                    "ok": all(state.ok for state in states) and not claim_problems,
                },
                indent=2,
            )
        )
    else:
        print(render(states, claim_problems, claim_notes))

    if not all(state.ok for state in states) or claim_problems:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
