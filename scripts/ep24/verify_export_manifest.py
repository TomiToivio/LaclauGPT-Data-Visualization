#!/usr/bin/env python3
"""Verify an EP24 export directory against the manifest that travels with it (#263 acceptance 4).

    python scripts/ep24/verify_export_manifest.py --root <export dir>
    python scripts/ep24/verify_export_manifest.py --root <export dir> --json verdict.json
    python scripts/ep24/verify_export_manifest.py --root <export dir> --require-verified   # cron/CI gate

Exit codes: ``0`` verified, ``1`` not verified (missing file, hash/size/row mismatch, layout mismatch or
ambiguity), ``2`` no usable manifest. ``--require-verified`` makes ``1``/``2`` the only pass/fail question, so
a nightly check can be wired straight into cron.

The output is aggregates and file names only: no row content is printed, so it can be quoted in a public
issue even when the export is private.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run from anywhere: this script lives two levels below the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from laclaugpt_visualization.ep24_manifest_verify import verify_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, help="export directory that should contain manifest.json")
    parser.add_argument("--json", help="write the full verdict to this path")
    parser.add_argument("--no-hashes", action="store_true",
                        help="skip hashing (size and rows only); a file whose bytes changed can then pass")
    parser.add_argument("--require-verified", action="store_true",
                        help="exit non-zero unless the verdict is 'verified'")
    args = parser.parse_args(argv)

    verdict = verify_manifest(args.root, hash_limit=0 if args.no_hashes else None)
    print(f"verdict: {verdict.verdict}")
    print(verdict.summary())
    for result in verdict.mismatched:
        print(f"  {result.status}: {result.path} — {result.detail}")
    if verdict.undeclared:
        print("undeclared: " + ", ".join(verdict.undeclared))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "verdict": verdict.verdict,
            "root": verdict.root,
            "layout_declared": verdict.layout_declared,
            "layout_detected": verdict.layout_detected,
            "files_declared": verdict.files_declared,
            "files_verified": verdict.files_verified,
            "rows_declared": verdict.rows_declared,
            "rows_verified": verdict.rows_verified,
            "undeclared": list(verdict.undeclared),
            "mismatched": [{"path": r.path, "status": r.status, "detail": r.detail}
                           for r in verdict.mismatched],
        }, indent=2) + "\n", encoding="utf-8")

    if verdict.verdict == "verified":
        return 0
    if verdict.verdict == "no manifest" and not args.require_verified:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
