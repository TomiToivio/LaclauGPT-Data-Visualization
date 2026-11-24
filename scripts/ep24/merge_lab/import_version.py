"""Load an explicitly selected approved revision for a legacy dashboard."""
import argparse
from pathlib import Path

from lab import read_rows, validate_export


def load_dashboard_rows(private_checkout, revision):
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("Select a positive revision number")
    directory = Path(private_checkout) / "analysis/ep24_legacy_curation/exports" / f"revision-{revision}"
    for path in validate_export(directory):
        yield from read_rows(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("private_checkout", type=Path)
    parser.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()
    print(sum(1 for _ in load_dashboard_rows(args.private_checkout, args.revision)), "validated dashboard rows")
