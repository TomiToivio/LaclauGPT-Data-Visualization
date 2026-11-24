"""Command line for the independent review panel (#311).

    python -m ep24_merge_lab.review freeze    --out <curation> [--profile <yaml> --root <private>]
    python -m ep24_merge_lab.review panel     --out <curation> [--limit N] [--concurrency 6]
    python -m ep24_merge_lab.review status    --out <curation>
    python -m ep24_merge_lab.review adjudicate --out <curation> [--limit N]
    python -m ep24_merge_lab.review reconcile --out <curation>
    python -m ep24_merge_lab.review release   --out <curation>

The panel needs models. They come from ``<curation>/reviewers.json`` when present, so a host can
name its own without the repository learning any endpoint:

    {"reviewers": [{"name": "A", "host": "127.0.0.1:11434", "model": "...", "style": "plain"},
                   {"name": "B", ...}, {"name": "C", ...}],
     "adjudicator": {"name": "adjudicator", "host": "127.0.0.1:11434", "model": "..."}}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ep24_merge_lab.review import (
    inventory,
    ledger,
    providers,
    reconcile,
    runner,
    wikipedia,
)
from ep24_merge_lab.review import (
    release as release_mod,
)


def _curation(args: argparse.Namespace) -> Path:
    return Path(args.out).expanduser()


def _latest_run(curation: Path) -> Path:
    marker = curation / "LATEST"
    if not marker.exists():
        raise SystemExit(f"no run in {curation}: run merge_labels.py run first")
    return curation / "runs" / marker.read_text(encoding="utf-8").strip()


def _panel(curation: Path) -> tuple[list[providers.Reviewer], providers.Reviewer]:
    config = curation / "reviewers.json"
    if not config.exists():
        raise SystemExit(
            f"no panel configured: write {config} with reviewers and an adjudicator "
            "(see the module docstring for the shape)"
        )
    payload = json.loads(config.read_text(encoding="utf-8"))
    reviewers = [
        providers.Reviewer(
            name=item.get("name", f"R{index}"),
            host=item["host"],
            model=item["model"],
            style=item.get("style", "plain"),
            temperature=float(item.get("temperature", 0.0)),
        )
        for index, item in enumerate(payload["reviewers"], start=1)
    ]
    adjudicator = providers.Reviewer(
        name=payload.get("adjudicator", {}).get("name", "adjudicator"),
        host=payload["adjudicator"]["host"],
        model=payload["adjudicator"]["model"],
    )
    return reviewers, adjudicator


def _freeze(args: argparse.Namespace) -> int:
    curation = _curation(args)
    run = Path(args.run).expanduser() if args.run else _latest_run(curation)
    units = inventory.units_from_run(run)
    if args.profile:
        from ep24_merge_lab import sources

        loaded = sources.load_profile(
            Path(args.profile).expanduser(),
            root=Path(args.root).expanduser() if args.root else None,
        )
        inventory.attach_countries(units, sources.extract(loaded))
    header = inventory.freeze(run, curation / "review" / "inventory.json", units)
    print(json.dumps(header, indent=2, sort_keys=True))
    return 0


def _load(curation: Path) -> tuple[dict, list[dict]]:
    header, units = inventory.load_inventory(curation / "review" / "inventory.json")
    return header, [unit.as_json() for unit in units]


def _panel_run(args: argparse.Namespace) -> int:
    curation = _curation(args)
    header, units = _load(curation)
    reviewers, _ = _panel(curation)
    if args.category:
        units = [unit for unit in units if unit["category"] == args.category]
    stats = runner.run(
        units,
        reviewers,
        curation / "review" / "ledger.jsonl",
        concurrency=args.concurrency,
        limit=args.limit,
        batch_size=args.batch_size,
        snapshot_sha256=header["digest"],
    )
    print(json.dumps({"inventory": header["digest"], **stats.as_json()}, indent=2))
    return 0


def _status(args: argparse.Namespace) -> int:
    curation = _curation(args)
    header, units = _load(curation)
    reviewers, _ = _panel(curation) if (curation / "reviewers.json").exists() else ([], None)
    coverage = ledger.coverage(
        curation / "review" / "ledger.jsonl", units, required=max(3, len(reviewers))
    )
    approved_path = curation / "review" / "approved.jsonl"
    print(
        json.dumps(
            {
                "inventory": header["digest"],
                "units": header["total"],
                "coverage": coverage,
                "approved": sum(1 for _ in approved_path.open(encoding="utf-8"))
                if approved_path.exists()
                else 0,
            },
            indent=2,
        )
    )
    return 0


def _adjudicate(args: argparse.Namespace) -> int:
    curation = _curation(args)
    _, units = _load(curation)
    _, adjudicator = _panel(curation)
    count = runner.adjudicate_disagreements(
        {unit["unit_id"]: unit for unit in units},
        curation / "review" / "ledger.jsonl",
        adjudicator,
        curation / "review" / "adjudications.jsonl",
        limit=args.limit,
    )
    print(json.dumps({"adjudicated": count}, indent=2))
    return 0


def _reconcile(args: argparse.Namespace) -> int:
    curation = _curation(args)
    header, units = _load(curation)
    reviewers, _ = _panel(curation)
    ledger_path = curation / "review" / "ledger.jsonl"
    approved, queue = reconcile.decide(
        units,
        ledger.reviews_by_unit(ledger_path),
        required=max(3, len(reviewers)),
        prior={},
    )
    adjudications = {}
    adjudication_path = curation / "review" / "adjudications.jsonl"
    if adjudication_path.exists():
        for line in adjudication_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                adjudications[item["unit_id"]] = item
    reconcile.attach_adjudications(queue, adjudications)

    for item in approved:
        if item.get("wikipedia_title"):
            match = wikipedia.verify(item["wikipedia_title"])
            item["wikipedia_title"] = match.title if match.exists else ""
            item["qid"] = match.qid
            item["wikipedia_url"] = match.url
        else:
            item["qid"] = ""
    coverage = ledger.coverage(ledger_path, units, required=max(3, len(reviewers)))
    reconcile.write_reports(curation / "review", approved, queue, coverage)
    print(
        json.dumps(
            {
                "inventory": header["digest"],
                "approved": len(approved),
                "human_queue": len(queue),
                "coverage": coverage,
            },
            indent=2,
        )
    )
    return 0


def _release(args: argparse.Namespace) -> int:
    curation = _curation(args)
    header, units = _load(curation)
    reviewers, _ = _panel(curation)
    approved: list[dict] = []
    path = curation / "review" / "approved.jsonl"
    if path.exists():
        approved = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    queue: list[dict] = []
    queue_path = curation / "review" / "human_queue.jsonl"
    if queue_path.exists():
        queue = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    coverage = ledger.coverage(
        curation / "review" / "ledger.jsonl", units, required=max(3, len(reviewers))
    )
    release_dir = release_mod.build(
        curation,
        approved=approved,
        human_queue=queue,
        coverage=coverage,
        inventory_header=header,
        reviews_path=curation / "review" / "ledger.jsonl",
        reviewer_models={reviewer.name: reviewer.model for reviewer in reviewers},
    )
    print(json.dumps({"release": str(release_dir)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze", help="freeze the inventory of decision units")
    freeze.add_argument("--out", required=True)
    freeze.add_argument("--run", default="")
    freeze.add_argument("--profile", default="")
    freeze.add_argument("--root", default="")
    freeze.set_defaults(func=_freeze)

    panel = sub.add_parser("panel", help="ask the reviewers about the units")
    panel.add_argument("--out", required=True)
    panel.add_argument("--limit", type=int, default=0)
    panel.add_argument("--concurrency", type=int, default=6)
    panel.add_argument("--category", default="")
    panel.add_argument("--batch-size", type=int, default=8, help="units per model call")
    panel.set_defaults(func=_panel_run)

    status = sub.add_parser("status", help="coverage of the panel so far")
    status.add_argument("--out", required=True)
    status.set_defaults(func=_status)

    adjudicate = sub.add_parser("adjudicate", help="resolve disagreements with the adjudicator")
    adjudicate.add_argument("--out", required=True)
    adjudicate.add_argument("--limit", type=int, default=0)
    adjudicate.set_defaults(func=_adjudicate)

    reconcile_cmd = sub.add_parser("reconcile", help="turn reviews into approved decisions")
    reconcile_cmd.add_argument("--out", required=True)
    reconcile_cmd.set_defaults(func=_reconcile)

    release_cmd = sub.add_parser("release", help="write an immutable release from the decisions")
    release_cmd.add_argument("--out", required=True)
    release_cmd.set_defaults(func=_release)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
