"""What a running dashboard deployment actually is, asked as questions a report can answer (#258).

Three times a live unit has been ``active``, answered 200, and served code nobody reviewed (#176, #185,
#234) — and once more on ``:8502``, where the checkout was three commits behind ``origin/main`` while the
service reported healthy. "Is my change live?" and "did my deploy work?" are therefore not questions about
the process exiting; they are questions about four separate facts:

* is the unit running, and from which working directory;
* is that checkout the reviewed commit;
* which snapshot is the data directory actually holding;
* does the port answer, and is the access gate on or off.

This module answers them as plain data so the CLI can print them, a test can assert them, and an agent can
report them without re-deriving the commands each time. Read-only: nothing here starts, stops, pulls or
writes. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

#: Environment variables that carry a dashboard access password. A set value is reported as "gated";
#: the value itself is never read, printed or logged.
PASSWORD_VARIABLES = ("LACLAUGPT_VIS_DEMO_PASSWORD", "LACLAUGPT_VIS_PASSWORD")


@dataclass
class Check:
    """One question, its answer, and whether the answer is a problem."""

    name: str
    ok: bool
    detail: str
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "problems": list(self.problems),
        }


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _git(root: Path, *args: str) -> str:
    result = _run(["git", "-C", str(root), *args])
    return result.stdout.strip() if result.returncode == 0 else ""


def checkout_drift(
    root: Path,
    *,
    expected_branch: str = "main",
    upstream_ref: str = "origin/main",
    fetch: bool = True,
) -> Check:
    """Is the serving checkout the reviewed commit on the expected branch?

    A deployment that is behind ``origin/main`` is serving code nobody reviewed for this host; a
    deployment ahead of it is serving code nobody reviewed anywhere. Both are reported, with counts, so
    the answer is actionable rather than a boolean.
    """
    if not (root / ".git").exists():
        return Check("checkout", False, f"{root} is not a git checkout", [f"no .git in {root}"])

    problems: list[str] = []
    if fetch and _run(["git", "-C", str(root), "fetch", "-q", "--prune", "origin"]).returncode != 0:
        problems.append("git fetch failed; drift compared against the local upstream ref")

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git(root, "rev-parse", "HEAD") or ""
    upstream = _git(root, "rev-parse", "--verify", "-q", upstream_ref) or ""

    if branch != expected_branch:
        problems.append(f"on branch {branch!r}, expected {expected_branch!r}")
    if not upstream:
        problems.append(f"{upstream_ref} not available; cannot assert drift")
        return Check("checkout", False, f"{branch} at {head[:7]}", problems)
    if head != upstream:
        ahead = _git(root, "rev-list", "--count", f"{upstream}..{head}") or "0"
        behind = _git(root, "rev-list", "--count", f"{head}..{upstream}") or "0"
        problems.append(
            f"serving {head[:7]}, {upstream_ref} is {upstream[:7]} ({ahead} ahead / {behind} behind)"
        )

    detail = f"{branch} at {head[:7]}" + (" == " + upstream_ref if head == upstream else "")
    return Check("checkout", not problems, detail, problems)


def data_snapshot(root: Path | str | None) -> Check:
    """Which export snapshot is the app reading, and does it declare itself?

    A snapshot without a manifest is not a snapshot: the manifest is what lets a reader name the run and
    compare counts. Its absence is reported even when the app is happily rendering.
    """
    if not root:
        return Check("data", False, "no data directory configured", ["data directory not set"])
    path = Path(root).expanduser()
    if not path.is_dir():
        return Check("data", False, str(path), [f"data directory missing: {path}"])

    manifest = path / "manifest.json"
    if not manifest.is_file():
        manifest = path / "MANIFEST.json"
    if not manifest.is_file():
        return Check("data", False, str(path), [f"no manifest.json/MANIFEST.json in {path}"])

    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Check("data", False, str(path), [f"manifest unreadable: {type(error).__name__}"])

    # Export manifests in this project name the run in more than one way: a `run_id`, a
    # `producer_revision` (the producer's run identifier) or a `version` (the export format). Report
    # whichever exists rather than "(unnamed)" -- a snapshot nobody can name is not auditable.
    run = (
        payload.get("run_id")
        or payload.get("run")
        or payload.get("producer_revision")
        or payload.get("version")
        or "(unnamed)"
    )
    rows = payload.get("exported_rows", payload.get("rows", payload.get("row_count")))
    if rows is None and isinstance(payload.get("countries"), dict):
        # Per-country counts are how the EP24 export declares its size: sum them, and keep the
        # country count visible so a missing country is not hidden behind a plausible total.
        video_counts = [
            country.get("exported_videos")
            for country in payload["countries"].values()
            if isinstance(country, dict)
        ]
        if all(isinstance(count, int) for count in video_counts) and video_counts:
            rows = sum(video_counts)
            detail = f"{path.name} run={run} videos={rows} over {len(video_counts)} countries"
            return Check("data", True, detail)

    detail = f"{path.name} run={run}" + (f" rows={rows}" if rows is not None else "")
    return Check("data", True, detail)


def unit_state(unit: str | None, *, user: bool = True, repo: Path | None = None) -> Check:
    """Is the unit active, and is its WorkingDirectory the checkout we think we are inspecting?"""
    if not unit:
        return Check("unit", True, "no unit given; skipped")
    scope = ["--user"] if user else []
    result = _run(
        ["systemctl", *scope, "show", unit, "-p", "ActiveState", "-p", "WorkingDirectory", "-p", "Environment"]
    )
    if result.returncode != 0:
        return Check("unit", False, unit, [f"systemctl could not describe {unit}"])

    values = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()

    problems: list[str] = []
    active = values.get("ActiveState", "unknown")
    if active != "active":
        problems.append(f"unit is {active}, not active")

    working = values.get("WorkingDirectory", "")
    if repo and working and Path(working).resolve() != repo.resolve():
        problems.append(f"unit runs from {working}, not {repo}")

    environment = values.get("Environment", "")
    gate = "ungated"
    for variable in PASSWORD_VARIABLES:
        if re.search(rf"(^|\s){variable}=\S", environment):
            gate = "password set"
            break

    detail = f"{unit} {active}" + (f", from {working}" if working else "") + f", {gate}"
    return Check("unit", not problems, detail, problems)


def health(port: int | None, host: str = "127.0.0.1", timeout: float = 5.0) -> Check:
    """Does the Streamlit health endpoint answer? A 200 on ``/`` is not the same test."""
    if not port:
        return Check("health", True, "no port given; skipped")
    url = f"http://{host}:{port}/_stcore/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(64).decode("utf-8", "replace").strip()
            status = response.status
    except (urllib.error.URLError, OSError) as error:
        return Check("health", False, url, [f"no answer: {type(error).__name__}"])
    ok = status == 200 and body.startswith("ok")
    return Check("health", ok, f"{url} -> {status} {body!r}", [] if ok else [f"health returned {status} {body!r}"])


def password_variable_from_environment() -> str | None:
    """The password variable present in *this* process's environment, if any. Value never returned."""
    for variable in PASSWORD_VARIABLES:
        if os.environ.get(variable):
            return variable
    return None


def report(
    *,
    repo: Path | None = None,
    unit: str | None = None,
    user_unit: bool = True,
    port: int | None = None,
    host: str = "127.0.0.1",
    data_dir: Path | str | None = None,
    fetch: bool = True,
) -> list[Check]:
    """Every question that decides whether a deployment is what it claims to be."""
    checks: list[Check] = []
    if unit:
        checks.append(unit_state(unit, user=user_unit, repo=repo))
    if repo:
        checks.append(checkout_drift(repo, fetch=fetch))
    if data_dir:
        checks.append(data_snapshot(data_dir))
    if port:
        checks.append(health(port, host=host))
    return checks


def render(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        mark = "ok  " if check.ok else "FAIL"
        lines.append(f"[{mark}] {check.name:9s} {check.detail}")
        for problem in check.problems:
            lines.append(f"        - {problem}")
    failed = sum(1 for check in checks if not check.ok)
    lines.append("")
    lines.append(f"{len(checks) - failed}/{len(checks)} checks ok" if checks else "nothing to check")
    return "\n".join(lines)
