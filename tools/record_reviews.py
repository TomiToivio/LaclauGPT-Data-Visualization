"""Record reviewer output into the shared ledger, and adjudicate it into the registry (#311).

Two steps, deliberately separate so each is auditable:

    record_reviews.py record --ledger L --batch batch-0001.json --reviews r.json --reviewer agent-a/run-7
    record_reviews.py adjudicate --ledger L --registry R --min-reviews 3

`record` refuses a review that does not cite the frozen snapshot's hash, so a reviewer who worked from
a different input cannot be counted. `adjudicate` writes only unanimous decisions; everything else is
reported as a conflict or a gap for a human, and the exit status is non-zero while any label in the
ledger is short of reviews.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboards"))

from ep24_merge_lab.ledger import Ledger, Review
from ep24_merge_lab.registry import Registry


def _batch_snapshot(batch_path: Path) -> tuple[str, str]:
    """The batch id and the sha256 recorded beside it when the batch was frozen."""
    digest_file = batch_path.with_suffix(".sha256")
    if not digest_file.exists():
        raise SystemExit(f"no snapshot hash beside {batch_path.name}; freeze the batch first")
    digest = digest_file.read_text(encoding="utf-8").split()[0]
    batch_id = json.loads(batch_path.read_text(encoding="utf-8")).get("batch_id", "")
    return batch_id, digest


def record(args: argparse.Namespace) -> int:
    batch_path = Path(args.batch)
    batch_id, digest = _batch_snapshot(batch_path)
    if args.snapshot and args.snapshot != digest:
        raise SystemExit(f"snapshot mismatch: batch says {digest[:16]}, you passed {args.snapshot[:16]}")

    payload = json.loads(Path(args.reviews).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("reviews") or payload.get("items") or []
    if not payload:
        raise SystemExit("no reviews in the file")

    reviews = []
    for item in payload:
        reviews.append(
            Review(
                batch_id=batch_id,
                label_id=str(item.get("label_id") or f"{item.get('category')}:{item.get('label')}"),
                category=str(item.get("category") or ""),
                label=str(item.get("label") or ""),
                reviewer=args.reviewer,
                decision=str(item.get("decision") or ""),
                canonical=str(item.get("canonical") or ""),
                wiki_title=str(item.get("wiki_title") or ""),
                wiki_url=str(item.get("wiki_url") or ""),
                wikidata_qid=str(item.get("wikidata_qid") or ""),
                fallback_reason=str(item.get("fallback_reason") or ""),
                polarity=str(item.get("polarity") or ""),
                evidence=tuple(item.get("evidence") or ()),
                confidence=float(item.get("confidence") or 0.0),
                reasoning=str(item.get("reasoning") or ""),
                snapshot_sha256=digest,
            )
        )
    ledger = Ledger.load(args.ledger) if Path(args.ledger).exists() else Ledger()
    ledger.append(reviews, args.ledger)
    matrix = Ledger.load(args.ledger).coverage_matrix()
    print(
        json.dumps(
            {"recorded": len(reviews), "reviewer": args.reviewer, "coverage": matrix}, indent=2, sort_keys=True
        )
    )
    return 0


def adjudicate(args: argparse.Namespace) -> int:
    ledger = Ledger.load(args.ledger)
    result = ledger.adjudicate(min_reviews=args.min_reviews)
    report = {
        "approved": len(result.approved),
        "keep_separate": len(result.keep_separate),
        "conflicts": len(result.conflicts),
        "incomplete": len(result.incomplete),
        "blocked_labels": ledger.blocked_labels(min_reviews=args.min_reviews),
        "conflict_detail": result.conflicts,
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.registry and result.entries:
        registry = Registry.load(args.registry) if Path(args.registry).exists() else Registry()
        # A settled decision supersedes a proposal, but must never overwrite another settled decision:
        # that is where a human's judgement or an earlier adjudication lives.
        SETTLED = {"approved", "keep_separate"}

        def already_settled(entry) -> bool:
            current = registry.latest(entry.category, entry.alias)
            if current is None:
                current = registry.latest(
                    entry.category,
                    entry.alias,
                    country=entry.scope.country,
                    language=entry.scope.language,
                    source=entry.scope.source,
                )
            return current is not None and current.status in SETTLED

        fresh = [entry for entry in result.entries if not already_settled(entry)]
        if fresh:
            registry.append(fresh, args.registry)
        print(f"\nwrote {len(fresh)} entries to {args.registry} ({len(result.entries) - len(fresh)} already decided)")
    return 1 if report["blocked_labels"] or report["conflicts"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="append one reviewer's output to the ledger")
    rec.add_argument("--ledger", required=True)
    rec.add_argument("--batch", required=True, help="the frozen batch json (its .sha256 is used)")
    rec.add_argument("--reviews", required=True, help="reviewer output json")
    rec.add_argument("--reviewer", required=True, help="attributable id, e.g. agent-a/run-7")
    rec.add_argument("--snapshot", default="", help="optional explicit snapshot hash to check")
    rec.set_defaults(func=record)

    adj = sub.add_parser("adjudicate", help="turn the ledger into registry entries")
    adj.add_argument("--ledger", required=True)
    adj.add_argument("--registry", default="")
    adj.add_argument("--min-reviews", type=int, default=3)
    adj.set_defaults(func=adjudicate)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
