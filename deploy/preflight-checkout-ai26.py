#!/usr/bin/env python3
"""Assert that the checkout about to serve AI26 is the one origin/main points at (#234).

Three times now the live ``:8501`` unit has drifted onto an old commit or a feature
branch (#176, #185, #234) and nothing noticed: the service was ``active``, the port
answered 200, and the preflight passed, because ``deploy/preflight-laskin-ai26.sh``
only verified that the checkout existed and that the CLI was installed. The second
half of #234 was the same blindness in the dependency direction: ``networkx`` was a
declared core dependency (``pyproject.toml``) that the serving venv did not have,
and the editable-install metadata was stale enough that ``pip``-style checks could
not see it either.

This script closes both holes for the deploy path in one fail-closed step:

* the serving checkout must be on ``main`` and equal to ``origin/main``;
* every requirement in ``[project].dependencies`` must be importable/installed at a
  satisfying version in the interpreter running this check (pass the service venv).

It reads ``pyproject.toml`` rather than installed distribution metadata on purpose:
the #234 defect was stale metadata that predated the dependency, so metadata is
exactly the source that lied.

Escape hatches, both explicit and both logged:

* ``LACLAUGPT_VIS_ALLOW_GIT_DRIFT=1`` - deploy a branch/commit on purpose;
* ``LACLAUGPT_VIS_GIT_FETCH=0`` - do not touch the network, compare against the
  local ``origin/main`` ref.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable
from importlib import metadata
from pathlib import Path

SKIP_VALUES = {"1", "true", "yes", "on"}
DISABLED_VALUES = {"0", "false", "no", "off"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in SKIP_VALUES


def _disabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in DISABLED_VALUES


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def checkout_problems(
    root: Path,
    *,
    fetch: bool = True,
    allow_drift: bool = False,
    expected_branch: str = "main",
    upstream_ref: str = "origin/main",
) -> list[str]:
    """Return the reasons the serving checkout is not the reviewed commit."""
    if allow_drift:
        return []

    problems: list[str] = []

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != expected_branch:
        problems.append(
            f"serving checkout is on branch {branch!r}, not {expected_branch!r}"
        )

    if fetch and _git(root, "fetch", "-q", "--prune", "origin").returncode != 0:
        print(
            "note: git fetch failed; drift is compared against the local "
            f"{upstream_ref} ref",
            file=sys.stderr,
        )

    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    upstream = _git(root, "rev-parse", "--verify", "-q", upstream_ref).stdout.strip()
    if not upstream:
        problems.append(
            f"{upstream_ref} is not available in the checkout; cannot assert deployment drift"
        )
        return problems
    if head != upstream:
        ahead = _git(root, "rev-list", "--count", f"{upstream}..{head}").stdout.strip()
        behind = _git(root, "rev-list", "--count", f"{head}..{upstream}").stdout.strip()
        problems.append(
            f"serving checkout is {head[:7]}, {upstream_ref} is {upstream[:7]} "
            f"({ahead or '0'} ahead / {behind or '0'} behind)"
        )
    return problems


def declared_dependencies(pyproject_path: Path) -> list[str]:
    """Core requirements from ``[project].dependencies``.

    Optional extras are deliberately ignored: they are configuration choices, and the
    #234 defect was about a core dependency.
    """
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return [str(item) for item in data.get("project", {}).get("dependencies") or []]


def _installed_version(name: str, version_getter: Callable[[str], str]) -> str | None:
    try:
        return version_getter(name)
    except (metadata.PackageNotFoundError, ImportError, LookupError):
        return None


def _satisfies(name: str, specifier: str, installed: str) -> bool:
    try:
        from packaging.requirements import Requirement
    except ImportError:  # pragma: no cover - packaging ships with streamlit
        return True
    return Requirement(f"{name}{specifier}").specifier.contains(
        installed, prereleases=True
    )


def dependency_problems(
    pyproject_path: Path,
    version_getter: Callable[[str], str] = metadata.version,
) -> list[str]:
    """Return the core dependencies that the serving interpreter cannot satisfy."""
    try:
        raw_requirements = declared_dependencies(pyproject_path)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"cannot read {pyproject_path.name}: {exc}"]

    try:
        from packaging.requirements import InvalidRequirement, Requirement
    except ImportError:  # pragma: no cover - packaging ships with streamlit
        InvalidRequirement = ValueError  # type: ignore[assignment,misc]
        Requirement = None  # type: ignore[assignment]

    problems: list[str] = []
    for raw in raw_requirements:
        if Requirement is None:
            name, specifier = raw.split(";")[0].strip(), ""
        else:
            try:
                requirement = Requirement(raw)
            except InvalidRequirement as exc:
                problems.append(f"unparsable core requirement {raw!r}: {exc}")
                continue
            if requirement.marker is not None and not requirement.marker.evaluate(
                {"extra": ""}
            ):
                continue
            name, specifier = requirement.name, str(requirement.specifier)

        installed = _installed_version(name, version_getter)
        if installed is None:
            problems.append(
                f"declared core dependency {name} is not installed in the serving venv"
            )
        elif specifier and not _satisfies(name, specifier, installed):
            problems.append(
                f"declared core dependency {name}{specifier} is installed as {installed}"
            )
    return problems


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed when the AI26 serving checkout drifts from origin/main "
        "or its core dependencies are missing (#234)."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pyproject", type=Path, default=None)
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        default=_flag("LACLAUGPT_VIS_ALLOW_GIT_DRIFT"),
        help="serve an intentional branch/commit (LACLAUGPT_VIS_ALLOW_GIT_DRIFT=1)",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        default=_disabled("LACLAUGPT_VIS_GIT_FETCH"),
        help="do not contact origin; compare with the local origin/main ref "
        "(LACLAUGPT_VIS_GIT_FETCH=0)",
    )
    parser.add_argument(
        "--skip-dependencies",
        action="store_true",
        help="only assert the checkout, not the installed core dependencies",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = args.repo_root.resolve()
    pyproject = (args.pyproject or root / "pyproject.toml").resolve()

    problems = checkout_problems(
        root, fetch=not args.no_fetch, allow_drift=args.allow_drift
    )
    if args.allow_drift:
        print(
            "note: git drift assertion skipped "
            "(LACLAUGPT_VIS_ALLOW_GIT_DRIFT=1); this deploy is not origin/main",
            file=sys.stderr,
        )
    if not problems:
        head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
        print(f"OK: serving checkout equals origin/main ({head})")

    if not args.skip_dependencies:
        dependency_failures = dependency_problems(pyproject)
        if not dependency_failures:
            print("OK: declared core dependencies are installed in the serving venv")
        problems.extend(dependency_failures)

    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
