"""Command line for the legacy EP24 merge lab (#300).

    python dashboards/ep24_merge_lab/merge_labels.py inventory --profile <private>/curation.yaml
    python dashboards/ep24_merge_lab/merge_labels.py run --profile <private>/curation.yaml \\
        --out <private>/analysis/ep24_legacy_curation [--dry-run] [--category person]
    python dashboards/ep24_merge_lab/merge_labels.py decide --out <same> \\
        --category person --action merge --canonical "Petteri Orpo" --member "Orpo" --reviewer tomi

Nothing here writes unless ``run`` is given ``--out`` and no ``--dry-run``; the profile and the
output directory both live in the private repository, so the public tree never learns a path.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):  # run as a script, as the README shows
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep24_merge_lab import curation, export, sources
from ep24_merge_lab.model import CATEGORIES
from ep24_merge_lab.similarity import RULES


def _profile(args: argparse.Namespace) -> list[sources.Source]:
    root = Path(args.root).expanduser() if getattr(args, "root", None) else None
    return sources.load_profile(Path(args.profile).expanduser(), root=root)


def _inventory(args: argparse.Namespace) -> int:
    rows = sources.inventory(_profile(args))
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    for row in rows:
        if not row.get("exists"):
            print(f"MISSING {row['source']:<24} {row['path']}")
            continue
        counts = ", ".join(f"{name}={count}" for name, count in row["distinct_labels"].items())
        print(
            f"{row['source']:<24} {row['kind']:<16} rows={row['rows']:<8} "
            f"bytes={row['bytes']:<11} {counts}"
        )
    return 0


def _run(args: argparse.Namespace) -> int:
    profile_path = Path(args.profile).expanduser()
    loaded = _profile(args)
    manifest_inputs = [
        {
            "source": source.name,
            "kind": source.kind,
            "path": str(source.path),
            "sha256": sources.file_digest(source.path) if source.path.exists() else "",
            "bytes": source.path.stat().st_size if source.path.exists() else 0,
        }
        for source in loaded
    ]
    rules = {
        name: replace(
            rule,
            auto_merge=args.min_auto if args.min_auto is not None else rule.auto_merge,
            review=args.review if args.review is not None else rule.review,
        )
        for name, rule in RULES.items()
    }

    pooled = sources.extract(loaded, category=args.category)
    out_dir = Path(args.out).expanduser() if args.out else None
    decisions = curation.load_decisions(out_dir / "decisions.jsonl") if out_dir else []
    results = {}
    for category in CATEGORIES:
        stats = pooled.get(category, [])
        if not stats:
            continue
        results[category] = curation.resolve_category(
            stats, category, decisions, rule=rules[category]
        )

    summary = {
        category: {
            "labels": len(pooled.get(category, [])),
            "clusters": len(result.clusters),
            "review": len(result.candidates),
            "singletons": len(result.singletons),
            "merged_labels": sum(len(cluster.members) for cluster in result.clusters),
        }
        for category, result in results.items()
    }
    if args.dry_run or out_dir is None:
        print(json.dumps({"dry_run": True, "summary": summary}, indent=2, sort_keys=True))
        return 0

    run_dir = curation.write_run(
        out_dir,
        results=results,
        rule_overrides=rules,
        manifest_inputs=manifest_inputs,
        profile_digest=sources.file_digest(profile_path),
    )
    print(json.dumps({"run": str(run_dir), "summary": summary}, indent=2, sort_keys=True))
    return 0


def _decide(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser()
    decision = curation.Decision(
        category=args.category,
        action=args.action,
        canonical=args.canonical or "",
        members=tuple(args.member or ()),
        reviewer=args.reviewer or "",
        at=datetime.now(UTC).isoformat(),
        note=args.note or "",
    )
    decision.validate()
    curation.append_decision(out_dir / "decisions.jsonl", decision)
    print(json.dumps({"recorded": asdict(decision)}, indent=2, sort_keys=True))
    return 0


def _export(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser()
    run = Path(args.run) if args.run else _latest_run(out_dir)
    decisions = curation.load_decisions(out_dir / "decisions.jsonl")
    result = export.build_export(run, decisions, out_dir, reviewer=args.reviewer, note=args.note)
    print(
        json.dumps(
            {
                "export": str(result.path),
                "export_id": result.path.name,
                "mapping_version": result.manifest["mapping_version"],
                "decisions": result.manifest["decisions"]["count"],
                "candidates_open": result.candidates_open,
                "totals": result.manifest["totals"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _activate(args: argparse.Namespace) -> int:
    payload = export.activate(Path(args.out).expanduser(), args.export_id, reviewer=args.reviewer)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("note: activation is a pointer; no dashboard file was written.")
    return 0


def _rollback(args: argparse.Namespace) -> int:
    payload = export.rollback(Path(args.out).expanduser(), reviewer=args.reviewer)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _status(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser()
    activation = export.current_activation(out_dir)
    active = export.resolve_active_export(out_dir)
    print(
        json.dumps(
            {
                "exports": export.list_exports(out_dir),
                "activation": activation,
                "active_export_resolves": bool(active),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _latest_run(out_dir: Path) -> Path:
    marker = out_dir / "LATEST"
    if not marker.exists():
        raise SystemExit(f"no run in {out_dir}: run merge_labels.py run first")
    return out_dir / "runs" / marker.read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="describe the configured legacy sources")
    inventory.add_argument("--profile", required=True)
    inventory.add_argument("--root", default="", help="resolve relative paths in the profile")
    inventory.add_argument("--json", action="store_true")
    inventory.set_defaults(func=_inventory)

    run = subparsers.add_parser("run", help="extract, merge and write a versioned run")
    run.add_argument("--profile", required=True)
    run.add_argument("--root", default="")
    run.add_argument("--out", default="", help="private curation directory (decisions.jsonl lives here)")
    run.add_argument("--category", choices=CATEGORIES, default=None)
    run.add_argument("--min-auto", type=float, default=None, help="override the auto-merge score")
    run.add_argument("--review", type=float, default=None, help="override the review-candidate score")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=_run)

    export_cmd = subparsers.add_parser("export", help="freeze the curated mapping into a version")
    export_cmd.add_argument("--out", required=True, help="curation directory (runs/ and exports/)")
    export_cmd.add_argument("--run", default="", help="run id; defaults to LATEST")
    export_cmd.add_argument("--reviewer", default="")
    export_cmd.add_argument("--note", default="")
    export_cmd.set_defaults(func=_export)

    activate = subparsers.add_parser("activate", help="point the adapter at one export")
    activate.add_argument("--out", required=True)
    activate.add_argument("--export", required=True, dest="export_id")
    activate.add_argument("--reviewer", default="")
    activate.set_defaults(func=_activate)

    rollback = subparsers.add_parser("rollback", help="withdraw activation")
    rollback.add_argument("--out", required=True)
    rollback.add_argument("--reviewer", default="")
    rollback.set_defaults(func=_rollback)

    status = subparsers.add_parser("status", help="what is exported and what is active")
    status.add_argument("--out", required=True)
    status.set_defaults(func=_status)

    decide = subparsers.add_parser("decide", help="record a researcher decision")
    decide.add_argument("--out", required=True)
    decide.add_argument("--category", choices=CATEGORIES, required=True)
    decide.add_argument("--action", choices=curation.ACTIONS, required=True)
    decide.add_argument("--canonical", default="")
    decide.add_argument("--member", action="append", default=None)
    decide.add_argument("--reviewer", default="")
    decide.add_argument("--note", default="")
    decide.set_defaults(func=_decide)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
