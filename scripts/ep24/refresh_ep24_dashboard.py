#!/usr/bin/env python3
"""Check, and optionally perform, an EP24 dashboard data refresh (#210).

    # is the dashboard showing the newest completed export?
    python scripts/ep24/refresh_ep24_dashboard.py \
        --dashboard /private/ep24/dashboard/export \
        --source    /private/ep24/mongo_export

    # fail instead of warning (use in CI or a cron health check)
    ... --require-current

    # replace the dashboard copy with the source, keeping a backup, then restart the unit
    ... --swap --restart-unit laclaugpt-ep24-demo

The comparison itself lives in `laclaugpt_visualization.ep24_refresh` so it can be unit-tested without a
database. This script is the thin operational shell around it: read two manifests, print a verdict, and
only touch files when explicitly asked with `--swap`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from laclaugpt_visualization.ep24_refresh import (
    RefreshError,
    annotate_manifest,
    compare,
    load_manifest,
)


def _print_report(report, *, verbose: bool) -> None:
    print(f"verdict: {report.verdict}   (refresh needed: {report.needs_refresh})")
    print(f"  dashboard: {report.dashboard_records} records, unit={report.dashboard_unit}, "
          f"generated {report.dashboard_generated_at}")
    print(f"  source:    {report.source_records} records, unit={report.source_unit}, "
          f"generated {report.source_generated_at}")
    if verbose:
        for country, (d_stats, s_stats) in report.per_country.items():
            d = "missing" if d_stats is None else f"{d_stats.records} rec / {d_stats.newest_timestamp}"
            s = "missing" if s_stats is None else f"{s_stats.records} rec / {s_stats.newest_timestamp}"
            print(f"  {country:<9} dashboard {d:<42} source {s}")
    for reason in report.reasons:
        print(f"  - {reason}")


def _swap(dashboard: Path, source: Path) -> Path:
    """Replace the dashboard copy with the source, keeping one backup. Returns the backup path."""
    if not dashboard.exists():
        raise RefreshError(f"dashboard directory does not exist: {dashboard}")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = dashboard.with_name(f"{dashboard.name}.prev-{stamp}")
    shutil.move(str(dashboard), str(backup))
    try:
        shutil.copytree(str(source), str(dashboard))
    except Exception:
        # Put the previous copy back rather than leaving the dashboard without data.
        shutil.rmtree(str(dashboard), ignore_errors=True)
        shutil.move(str(backup), str(dashboard))
        raise
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or perform an EP24 dashboard refresh (#210).")
    parser.add_argument("--dashboard", required=True, type=Path,
                        help="directory the dashboard reads (contains MANIFEST.json)")
    parser.add_argument("--source", required=True, type=Path,
                        help="directory of the newest completed export")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--require-current", action="store_true",
                        help="exit 1 unless the dashboard is current")
    parser.add_argument("--swap", action="store_true",
                        help="replace the dashboard copy with the source (keeps a backup)")
    parser.add_argument("--restart-unit", default=None,
                        help="systemd --user unit to restart after a successful swap")
    parser.add_argument("--verbose", action="store_true", help="print per-country detail")
    parser.add_argument("--force", action="store_true",
                        help="swap even when the manifests do not show staleness "
                             "(e.g. step-level reprocessing that leaves counts unchanged)")
    parser.add_argument("--annotate", action="store_true",
                        help="count the dashboard's per-country CSVs into its MANIFEST.json first")
    args = parser.parse_args(argv)

    if args.annotate:
        try:
            written = annotate_manifest(args.dashboard)
        except RefreshError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"annotated {args.dashboard}/MANIFEST.json: {written.get('countries')}")

    try:
        report = compare(load_manifest(args.dashboard), load_manifest(args.source))
    except RefreshError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report, verbose=args.verbose)

    if args.swap:
        if report.verdict == "incomparable":
            print("refusing to swap: the source manifest is not usable", file=sys.stderr)
            return 2
        if not report.needs_refresh and not args.force:
            print("nothing to swap: the dashboard already matches the source "
                  "(use --force for step-level refreshes the manifests cannot see)")
        else:
            backup = _swap(args.dashboard, args.source)
            print(f"swapped: {args.dashboard} <- {args.source} (backup at {backup})")
            if args.restart_unit:
                subprocess.run(["systemctl", "--user", "restart", args.restart_unit], check=False)
                print(f"restarted unit {args.restart_unit}")

    if args.require_current and report.needs_refresh:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
