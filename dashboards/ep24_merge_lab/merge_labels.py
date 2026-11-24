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
from ep24_merge_lab.model import CATEGORIES, LabelStat, MergeResult
from ep24_merge_lab.registry import Registry
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


def _freeze(args: argparse.Namespace) -> int:
    """Hash the input inventory of a run and write it beside that run (#311).

    Read-only with respect to the corpus: it re-hashes what the run recorded, counts what was
    reviewed, and writes one document. A changed or missing file is reported in `integrity`, never
    repaired, because a freeze exists to make exactly that impossible to overlook.
    """
    from ep24_merge_lab import freeze as freeze_mod

    profile_path = Path(args.profile).expanduser()
    curation = Path(args.out).expanduser()
    run_dir = Path(args.run).expanduser()
    if not run_dir.is_absolute():
        run_dir = curation / "runs" / str(args.run)
    if not run_dir.is_dir():
        print(f"no such run directory: {run_dir}", file=sys.stderr)
        return 2

    document = freeze_mod.freeze(
        profile=_profile(args),
        profile_path=profile_path,
        run_dir=run_dir,
    )
    target = freeze_mod.write(document, run_dir / "inventory.json")
    print(f"wrote {target}")
    print(freeze_mod.summarize(document))
    return 0 if (document.get("integrity") or {}).get("frozen") else 1


def _run(args: argparse.Namespace) -> int:
    profile_path = Path(args.profile).expanduser()
    loaded = _profile(args)
    missing = [source.name for source in loaded if not source.path.is_file()]
    if not loaded or missing:
        # Fail with a sentence instead of a traceback: this runs from a unit's ExecStart too.
        raise SystemExit(
            "not every configured legacy source is present: "
            + (", ".join(missing) or "the profile lists no sources")
            + " — hydrate the private data first"
        )
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

    # Human-verified Excel codebooks are read before anything is clustered (#311 section 8). A
    # workbook row is a decision, so it is applied as a forced merge and its provenance is
    # carried into the run; conflicts are queued instead of resolved.
    workbook = None
    workbook_info: dict[str, object] = {"used": False}
    workbooks_dir = getattr(args, "workbooks", "") or ""
    if workbooks_dir:
        from ep24_merge_lab import workbook_evidence, workbook_mappings

        evidence = workbook_evidence.inspect_workbooks(Path(workbooks_dir).expanduser())
        workbook = workbook_mappings.from_evidence(evidence)
        workbook_info = {
            "used": True,
            "directory": str(workbooks_dir),
            "files": {
                category: {
                    "file": source["file"],
                    "sha256": source["sha256"],
                    "bytes": source["bytes"],
                    "pairs": len(source["pairs"]),
                }
                for category, source in evidence["sources"].items()
            },
            "counts": workbook.counts,
            "adjudication_open": len(workbook.adjudication),
        }

    registry_info: dict[str, object] = {"pinned": False}
    registry_aliases: dict[str, dict[str, list[dict[str, object]]]] = {}
    registry_path = getattr(args, "registry", "") or ""
    if not registry_path and getattr(args, "require_registry", False):
        raise SystemExit("--require-registry was given but --registry was not")
    if registry_path:
        registry = Registry.load(registry_path)
        applied, registry_aliases = _apply_registry(pooled, registry, loaded)
        registry_info = {
            "pinned": True,
            "path": str(registry_path),
            "version": registry.version,
            "entries": len(registry.entries),
            "labels_rewritten": applied,
            "original_aliases_kept": sum(len(items) for by_original in registry_aliases.values() for items in by_original.values()),
        }
    out_dir = Path(args.out).expanduser() if args.out else None
    decisions = curation.load_decisions(out_dir / "decisions.jsonl") if out_dir else []
    results = {}
    for category in CATEGORIES:
        stats = pooled.get(category, [])
        if not stats:
            continue
        results[category] = curation.resolve_category(
            stats, category, decisions, rule=rules[category], workbook=workbook
        )

    summary = {
        category: {
            "labels": len(pooled.get(category, [])),
            "clusters": len(result.clusters),
            "review": len(result.candidates),
            "singletons": len(result.singletons),
            "merged_labels": sum(len(cluster.members) for cluster in result.clusters),
            "workbook_clusters": sum(
                1 for cluster in result.clusters if "workbook" in cluster.method.split("+")
            ),
        }
        for category, result in results.items()
    }
    coverage = _workbook_coverage(workbook, pooled, results) if workbook else None
    if args.dry_run or out_dir is None:
        payload: dict[str, object] = {"dry_run": True, "summary": summary}
        if coverage:
            payload["workbook_coverage"] = coverage
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    run_dir = curation.write_run(
        out_dir,
        results=results,
        rule_overrides=rules,
        manifest_inputs=manifest_inputs,
        profile_digest=sources.file_digest(profile_path),
        registry=registry_info,
        workbook=workbook.as_json() if workbook else None,
        coverage=coverage,
        registry_aliases=registry_aliases,
        workbook_inputs=workbook_info,
        label_counts={category: len(stats) for category, stats in pooled.items()},
    )
    print(json.dumps({"run": str(run_dir), "summary": summary}, indent=2, sort_keys=True))
    return 0


def _workbook_coverage(
    workbook: object,
    pooled: dict[str, list[LabelStat]],
    results: dict[str, MergeResult],
) -> dict[str, object]:
    """How much of the corpus the human workbooks actually reach, per category.

    ``matched`` is the count of distinct corpus labels whose spelling a workbook row names.
    ``matcher_only`` is the count of clusters the matcher made without any human row — the number
    that has to be reviewed before a release can claim workbook grounding.
    """
    document = workbook.as_json()  # type: ignore[attr-defined]
    report: dict[str, object] = {}
    for category in ("entity", "person", "theme"):
        entries = document["forced"].get(category) or []
        if not entries:
            continue
        aliases = {alias for entry in entries for alias in entry["members"]}
        observed = {stat.label: stat.count for stat in pooled.get(category, [])}
        folded = {" ".join(label.split()).casefold(): label for label in observed}
        matched = sorted(folded[key] for key in aliases if key in folded)
        result = results.get(category)
        clusters = result.clusters if result else []
        report[category] = {
            "workbook_rows": document["counts"][category]["rows"],
            "workbook_groups": len(entries),
            "workbook_aliases": len(aliases),
            "observed_labels": len(observed),
            "matched": len(matched),
            "unmatched": len(observed) - len(matched),
            "unused_workbook_aliases": len(aliases) - len(matched),
            "occurrences_matched": sum(observed[label] for label in matched),
            "occurrences_total": sum(observed.values()),
            "clusters_total": len(clusters),
            "clusters_with_workbook": sum(
                1 for cluster in clusters if "workbook" in cluster.method.split("+")
            ),
            "clusters_matcher_only": sum(
                1 for cluster in clusters if "workbook" not in cluster.method.split("+")
            ),
            "adjudication_open": sum(
                1
                for item in document["adjudication"]
                if item.get("category") == category
            ),
        }
    return report


def _apply_registry(
    pooled: dict[str, list[LabelStat]],
    registry: Registry,
    loaded: list[sources.Source],
) -> tuple[int, dict[str, dict[str, list[dict[str, object]]]]]:
    """Rewrite labels through the shared registry before anything is clustered.

    The registry is the authority: a mapping a human approved, or that reviewers settled, must reach
    the canonical tables without the similarity rules rediscovering it. Labels it does not mention keep
    their spelling and stay eligible for review.

    The rewrite is *not* allowed to erase the corpus spellings it collapsed. Every rewritten label is
    returned as ``category -> canonical -> [{alias, occurrences}]`` so the run can keep an
    alias-to-canonical row for it; otherwise the canonical table would name a label that nothing in
    the corpus actually says, and the provenance of the collapse would be gone.
    """
    single_source = loaded[0].name if len(loaded) == 1 else ""
    rewritten = 0
    kept: dict[str, dict[str, list[dict[str, object]]]] = {}
    for category, stats in pooled.items():
        regrouped: dict[tuple[str, str], LabelStat] = {}
        for stat in stats:
            country = stat.countries[0] if len(stat.countries) == 1 else ""
            canonical = registry.map_label(category, stat.label, country=country, source=single_source)
            if canonical != stat.label:
                rewritten += 1
                kept.setdefault(category, {}).setdefault(canonical, []).append(
                    {
                        "alias": stat.label,
                        "occurrences": stat.count,
                        "polarity": stat.polarity,
                        "countries": list(stat.countries),
                    }
                )
                stat = LabelStat(
                    label=canonical,
                    count=stat.count,
                    countries=stat.countries,
                    polarity=stat.polarity,
                )
            key = (stat.polarity, stat.label)
            existing = regrouped.get(key)
            regrouped[key] = (
                stat
                if existing is None
                else LabelStat(
                    label=existing.label,
                    count=existing.count + stat.count,
                    countries=tuple(sorted(set(existing.countries) | set(stat.countries))),
                    polarity=existing.polarity,
                )
            )
        pooled[category] = sorted(regrouped.values(), key=lambda item: (-item.count, item.label))
    return rewritten, kept


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


def _check(args: argparse.Namespace) -> int:
    """Answer one question fast, without writing anything: can the lab start?

    This is what a unit's ``ExecStartPre`` should call. Re-running the merge on every start would
    change the tables under a reviewer with an open session, so the preflight only looks.
    """
    loaded = _profile(args)
    missing = [source.name for source in loaded if not source.path.is_file()]
    if not loaded or missing:
        print(
            "MISSING sources: " + (", ".join(missing) or "profile lists no sources"),
            file=sys.stderr,
        )
        return 1
    if not args.out:
        print(f"ok: {len(loaded)} sources configured", file=sys.stderr)
        return 0
    out_dir = Path(args.out).expanduser()
    try:
        run = _latest_run(out_dir)
    except SystemExit:
        print(f"MISSING run in {out_dir}: run merge_labels.py run first", file=sys.stderr)
        return 1
    decisions = len(curation.load_decisions(out_dir / "decisions.jsonl"))
    print(
        f"ok: {len(loaded)} sources, run {run.name}, {decisions} decisions",
        file=sys.stderr,
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

    freeze_cmd = subparsers.add_parser(
        "freeze", help="hash a run's input inventory and state the review obligation (#311)"
    )
    freeze_cmd.add_argument("--profile", required=True)
    freeze_cmd.add_argument("--root", default="")
    freeze_cmd.add_argument("--out", required=True, help="curation directory (runs/ live beneath it)")
    freeze_cmd.add_argument("--run", required=True, help="run id under runs/, or a path to one")
    freeze_cmd.set_defaults(func=_freeze)

    run = subparsers.add_parser("run", help="extract, merge and write a versioned run")
    run.add_argument("--profile", required=True)
    run.add_argument("--root", default="")
    run.add_argument("--out", default="", help="private curation directory (decisions.jsonl lives here)")
    run.add_argument("--category", choices=CATEGORIES, default=None)
    run.add_argument("--min-auto", type=float, default=None, help="override the auto-merge score")
    run.add_argument("--review", type=float, default=None, help="override the review-candidate score")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--registry", default="", help="shared merge registry (jsonl) to apply and record")
    run.add_argument(
        "--workbooks",
        default="",
        help="directory holding the human Excel codebooks (entities/persons/themes.xlsx)",
    )
    run.add_argument(
        "--require-registry",
        action="store_true",
        help="fail instead of running unpinned when --registry is not given",
    )
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

    check = subparsers.add_parser("check", help="preflight: are the sources and a run present?")
    check.add_argument("--profile", required=True)
    check.add_argument("--root", default="")
    check.add_argument("--out", default="")
    check.set_defaults(func=_check)

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
