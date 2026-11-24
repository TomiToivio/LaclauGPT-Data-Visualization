"""Curate legacy EP24 labels: propose merges across persons, entities, themes, topics, sentiments.

    python tools/legacy_curate.py --source export.csv --category persons --category entities \
        --out analysis/ep24_legacy_curation --dry-run

The source is read-only. Outputs land in ``--out``: canonical.csv, aliases.csv,
review_queue.csv and summary.json. ``--decisions`` points at a JSON file holding confirmed merges
and explicit keep-separates; those decisions are honoured on every re-run, so review is not lost
work. ``--dry-run`` reports statistics without writing anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laclaugpt_visualization.legacy_curation import (
    CATEGORIES,
    CurationSettings,
    curate,
    read_labels,
    write_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="CSV/JSON/JSONL export (read-only)")
    parser.add_argument("--out", type=Path, required=True, help="working directory for the outputs")
    parser.add_argument(
        "--category", action="append", choices=CATEGORIES,
        help="repeatable; defaults to all five",
    )
    parser.add_argument("--delimiter", default=",", help="CSV delimiter (default ',')")
    parser.add_argument("--auto", type=float, default=0.95, help="confidence to merge without review")
    parser.add_argument("--review", type=float, default=0.70, help="confidence to queue for review")
    parser.add_argument("--decisions", type=Path, help="JSON with manual merges and keep-separates")
    parser.add_argument("--dry-run", action="store_true", help="report statistics, write nothing")
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.error(f"source not found: {args.source}")

    categories = args.category or list(CATEGORIES)
    labelled: dict[str, Counter[str]] = {}
    for category in categories:
        counts = read_labels(args.source, category, delimiter=args.delimiter)
        if counts:
            labelled[category] = counts

    if not labelled:
        print("no labels found for the requested categories", file=sys.stderr)
        return 2

    decisions = {}
    if args.decisions and args.decisions.exists():
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))

    result = curate(
        labelled,
        settings=CurationSettings(auto=args.auto, review=args.review),
        decisions=decisions,
    )

    for category, stats in result["stats"].items():  # type: ignore[union-attr]
        print(
            f"{category:10s} labels={stats['labels']:6d} auto={stats['auto_merges']:5d} "
            f"review={stats['review_candidates']:5d} collapsed={stats['labels_collapsed']:5d} "
            f"after={stats['distinct_after']:6d}"
        )

    paths = write_outputs(result, args.out, dry_run=args.dry_run)
    if paths:
        for name, path in paths.items():
            print(f"wrote {name}: {path}")
    else:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
