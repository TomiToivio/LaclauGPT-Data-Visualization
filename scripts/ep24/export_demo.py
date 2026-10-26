#!/usr/bin/env python3
"""EP24 FI/PL/PT demo export — the documented entrypoint (issue #195, Part 1).

This is a **thin adapter**, not a second exporter. The implementation lives in
`scripts/ep24/export_visualization_data.py` (streaming, two-pass primary-row selection, coverage
manifest, child tables). This wrapper exists because the runbook and the deployment examples call
`export_demo.py --finland … --poland … --portugal … --output …`, and because real exports need two
things the earlier version got wrong:

* **country values in the producer's own casing** — a real Polish frame says `Poland`, not `poland`,
  and a real shared frame holds every country, so an exact lowercase match aborted the whole export;
* **a shared source file** — the Portuguese rows live inside the shared `:8501` export, so a country
  needs to be selected out of a file that also carries Finland, Poland, Sweden, …

Both are handled here without changing the documented CLI. Extra flags:
`--filter-country VALUE` (repeatable, `country=Value`) and `--profile` (`reprocessed`/`legacy`).

Usage:

    python scripts/ep24/export_demo.py \\
        --finland /private/input/finland.csv \\
        --poland  /private/input/poland.csv:legacy \\
        --portugal /private/input/shared_8501.csv:legacy \\
        --filter-country portugal=Portugal \\
        --output /private/LaclauGPT-Private/analysis/ep24/dashboard/export
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_visualization_data import COUNTRIES
from export_visualization_data import main as export_main


def build_argv(args: argparse.Namespace) -> list[str]:
    argv: list[str] = []
    for country in COUNTRIES:
        spec = getattr(args, country, None)
        if spec:
            argv += ["--source", f"{country}={spec}"]
    for pair in args.filter_country:
        argv += ["--filter-country", pair]
    if args.profile:
        argv += ["--profile", args.profile]
    argv += ["--output", str(args.output)]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for country in COUNTRIES:
        parser.add_argument(f"--{country}", type=str, default=None, metavar="PATH[:PROFILE]",
                            help="Roihu cumulative CSV, or a legacy/shared frame with :legacy")
    parser.add_argument("--output", type=Path, required=True, help="private output directory")
    parser.add_argument("--filter-country", action="append", default=[], metavar="COUNTRY=VALUE",
                        help="keep only rows whose in-file country equals VALUE")
    parser.add_argument("--profile", choices=("reprocessed", "legacy"), default=None,
                        help="profile for sources without a :profile suffix")
    args = parser.parse_args(argv)
    if not any(getattr(args, country, None) for country in COUNTRIES):
        parser.error("at least one of --finland/--poland/--portugal is required")
    return export_main(build_argv(args))


if __name__ == "__main__":
    raise SystemExit(main())
