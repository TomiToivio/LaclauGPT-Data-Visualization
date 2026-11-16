#!/usr/bin/env python3
"""Report what a dashboard deployment actually is — before or after a deploy (#258).

Read-only. It starts, stops, pulls and writes nothing; it answers the four questions that decide whether a
change is live: is the unit running and from where, is that checkout the reviewed commit, which export
snapshot is being read, and does the port answer with the access gate on or off.

Study-neutral on purpose: nothing about a particular study, host or port is baked in, and the deployment
state of any instance belongs in private deployment configuration rather than in this public repository.

    # on the serving host, for a systemd user unit
    python deploy/report-served-state.py \
        --unit laclaugpt-visualization.service \
        --repo /srv/laclaugpt/visualization \
        --data-dir /srv/laclaugpt/private/analysis/<study>/dashboard/export \
        --port 8501

    # from anywhere, against a remote host, without leaving the read-only contract
    ssh <host> 'cd <checkout> && python deploy/report-served-state.py --unit ... --port ...'

Exit codes: 0 everything ok, 1 at least one check failed, 2 the invocation itself is wrong.

Privacy: paths, branch names, commit abbreviations, run identifiers and row counts only. No export content,
no author names, no credentials — a password is reported as "password set", never by value.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from served_state import password_variable_from_environment, render, report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unit", help="systemd unit name (checked with --user by default)")
    parser.add_argument("--system-unit", action="store_true", help="treat --unit as a system unit")
    parser.add_argument("--repo", type=Path, help="the checkout the unit serves")
    parser.add_argument("--data-dir", type=Path, help="the snapshot directory the app reads")
    parser.add_argument("--port", type=int, help="the port to health-check")
    parser.add_argument("--host", default="127.0.0.1", help="host to health-check (default 127.0.0.1)")
    parser.add_argument("--no-fetch", action="store_true", help="do not git fetch before comparing drift")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if not any((args.unit, args.repo, args.data_dir, args.port)):
        parser.error("ask at least one question: --unit, --repo, --data-dir or --port")

    checks = report(
        repo=args.repo,
        unit=args.unit,
        user_unit=not args.system_unit,
        port=args.port,
        host=args.host,
        data_dir=args.data_dir,
        fetch=not args.no_fetch,
    )

    if args.json:
        print(json.dumps({"checks": [check.as_dict() for check in checks]}, indent=1))
    else:
        print(render(checks))
        gate = password_variable_from_environment()
        if gate:
            print(f"\nnote: {gate} is set in this shell; the serving unit's gate is reported above.")

    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
