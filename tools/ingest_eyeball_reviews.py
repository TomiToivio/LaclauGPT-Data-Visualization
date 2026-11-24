"""Ingest the sibling "eyeball" review passes into the shared ledger and registry (#311).

Three single-pass reports live in ``analysis/ep24_legacy_curation/eyeball_reviews/``, each in its own
shape:

* ``single-pass-codebook`` — ``candidates`` (alias -> canonical label + Wikipedia URL) and ``flags``
  (collision warnings: "CDU" in Portugal is not the German CDU).
* ``second-codebook-pass`` — ``proposals`` (alias -> proposed canonical + reference URL) and
  ``keep_separate_checks`` (free-text cluster descriptions).
* ``third-registry-peer-pass`` — ``findings`` over already-registered rows, e.g. a
  ``support_same_identity`` vote for BG:Borisov/Borissov.

Two principles govern the ingest:

1. **No invented provenance.** These passes reviewed *older codebooks*, not the current corpus, so each
   becomes its own batch whose provenance string says exactly what was seen. Mixing them into a
   three-review quorum with the corpus reviews would be a lie the ledger would then enforce.
2. **No invented scope.** A flag names an alias, a country and a reason, but not a category; the category
   is resolved from the frozen inventory when the alias occurs in exactly one category, and the item is
   reported as unmapped otherwise.

Everything ingested is one *single* review. It never becomes an ``approved`` decision — the ledger's
three-review rule sees to that — but it is visible to the Merge Lab as a ``proposed`` registry entry so a
human can act on it now.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboards"))

from ep24_merge_lab.ledger import Ledger, Review
from ep24_merge_lab.registry import Registry, RegistryEntry, Scope

CATEGORIES = ("entity", "person", "theme", "topic", "sentiment")


@dataclass
class Ingested:
    reviews: list[Review]
    proposed: list[RegistryEntry]
    unmapped: list[dict[str, Any]]
    batch_id: str
    provenance: str


def _provenance(document: dict[str, Any], filename: str) -> str:
    """A description of what the reviewer actually saw, in place of a snapshot hash it never had."""
    bits = []
    for key in ("review_scope", "scope"):
        if document.get(key):
            bits.append(str(document[key]))
    if document.get("latest_run"):
        bits.append(f"latest_run:{document['latest_run']}")
    if document.get("registry_blob_sha"):
        bits.append(f"registry_blob:{document['registry_blob_sha'][:12]}")
    return f"{filename}: " + " | ".join(bits) if bits else filename


def _reviewer_of(document: dict[str, Any], item: dict[str, Any], filename: str) -> str:
    if item.get("reviewer"):
        return f"{item['reviewer']}/{filename}"
    ids = item.get("reviewer_ids") or []
    if ids:
        return f"{ids[0]}/{filename}"
    if document.get("reviewer"):
        return f"{document['reviewer']}/{filename}"
    return f"unknown-reviewer/{filename}"


def _urls(item: dict[str, Any]) -> list[str]:
    found = []
    for key in ("wikipedia_url", "reference_to_verify"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith("http"):
            found.append(value)
    for value in item.get("sources") or ():
        if isinstance(value, str) and value.startswith("http"):
            found.append(value)
    return found


def _evidence(item: dict[str, Any]) -> tuple[str, ...]:
    bits = []
    for key in ("evidence", "note", "reason"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            bits.append(value.strip())
    bits.extend(_urls(item))
    return tuple(dict.fromkeys(bits))


def _category_inventory(run_dir: Path | None) -> dict[str, set[str]]:
    """Which categories each label belongs to, from the frozen canonical tables."""
    inventory: dict[str, set[str]] = defaultdict(set)
    if run_dir is None:
        return inventory
    for category in CATEGORIES:
        path = run_dir / f"canonical_{category}.csv"
        if not path.exists():
            continue
        for row in csv.DictReader(path.open(encoding="utf-8", newline="")):
            for member in (row["canonical"], *(row.get("members") or "").split(" | ")):
                member = member.strip()
                if member:
                    inventory[member.casefold()].add(category)
    return inventory


def _resolve_category(
    alias: str, stated: str, inventory: dict[str, set[str]]
) -> tuple[str, str]:
    """The category a label belongs to, or a reason why it cannot be decided."""
    if stated in CATEGORIES:
        return stated, ""
    found = inventory.get(alias.casefold(), set())
    if len(found) == 1:
        return next(iter(found)), ""
    if not found:
        return "", f"alias not present in the frozen inventory ({alias!r})"
    return "", f"alias occurs in several categories ({sorted(found)})"


def parse_document(
    document: dict[str, Any], filename: str, inventory: dict[str, set[str]]
) -> Ingested:
    """Map one eyeball report onto reviews, proposed entries, and an unmapped report."""
    batch_id = f"eyeball-{Path(filename).stem}"
    provenance = _provenance(document, Path(filename).stem)
    reviews: list[Review] = []
    proposed: list[RegistryEntry] = []
    unmapped: list[dict[str, Any]] = []

    def add(
        item: dict[str, Any],
        *,
        alias: str,
        canonical: str,
        decision: str,
        reason: str = "",
    ) -> None:
        category, why = _resolve_category(alias, str(item.get("category") or ""), inventory)
        if not category:
            unmapped.append({"file": filename, "alias": alias, "reason": why, "raw": item})
            return
        urls = _urls(item)
        evidence = _evidence(item)
        fallback = reason or (
            "" if urls else "this pass cited no URL; its own text is the only evidence it supplied"
        )
        scope_raw: dict[str, Any] = item["scope"] if isinstance(item.get("scope"), dict) else {}
        country = str(scope_raw.get("country") or item.get("country") or "")
        reviewer = _reviewer_of(document, item, Path(filename).stem)
        reviews.append(
            Review(
                batch_id=batch_id,
                label_id=f"{category}:{alias}",
                category=category,
                label=alias,
                reviewer=reviewer,
                decision=decision,
                canonical=canonical,
                wiki_title="",
                wiki_url=urls[0] if urls else "",
                wikidata_qid="",
                fallback_reason=fallback,
                evidence=evidence,
                confidence=0.0,  # the passes state no confidence; inventing one would be worse
                reasoning=str(item.get("status") or item.get("decision") or ""),
                snapshot_sha256=provenance,
            )
        )
        if decision == "merge" and canonical:
            proposed.append(
                RegistryEntry(
                    category=category,
                    alias=alias,
                    canonical=canonical,
                    status="proposed",
                    wiki_url=urls[0] if urls else "",
                    fallback_reason=fallback,
                    scope=Scope(country=country) if country else Scope(),
                    evidence=evidence or ("single-pass eyeball review",),
                    reviewers=(reviewer,),
                    method="eyeball-single-pass",
                    decision="merge",
                )
            )

    # shape 1: candidates + flags
    for item in document.get("candidates") or ():
        alias = str(item.get("alias") or "")
        if alias:
            add(item, alias=alias, canonical=str(item.get("canonical_label") or ""), decision="merge")
    for item in document.get("flags") or ():
        alias = str(item.get("alias") or "")
        if not alias:
            # Several flags are cluster-level guidance ("keep Fidesz, the Fidesz-KDNP alliance and the
            # Fidesz government distinct") with no single alias to attach to. They cannot become label
            # reviews, but dropping them silently would lose a real judgement.
            unmapped.append(
                {
                    "file": filename,
                    "alias": f"(cluster flag, {item.get('country') or '?'})",
                    "reason": "flag names no single alias; cluster-level guidance",
                    "raw": item,
                }
            )
            continue
        add(
            item,
            alias=alias,
            canonical="",
            decision="keep_separate",
            reason=str(item.get("reason") or "collision warning"),
        )

    # shape 2: proposals + free-text keep-separate checks
    for item in document.get("proposals") or ():
        alias = str(item.get("alias") or "")
        if alias:
            add(item, alias=alias, canonical=str(item.get("proposed_canonical") or ""), decision="merge")
    for check in document.get("keep_separate_checks") or ():
        unmapped.append(
            {
                "file": filename,
                "alias": str(check),
                "reason": "free-text cluster description, not a label-scoped decision",
            }
        )

    # shape 3: findings over registered rows
    for item in document.get("findings") or ():
        # shape 4: a code audit ("severity"/"file"/"finding") has no label decisions at all. It must be
        # surfaced, never counted as a review and never silently discarded.
        if item.get("severity") and item.get("file"):
            unmapped.append(
                {
                    "file": filename,
                    "alias": f"(code finding: {item.get('file')})",
                    "reason": f"code audit finding, severity={item.get('severity')}: {item.get('finding')}",
                    "raw": item,
                }
            )
            continue
        labels = [str(label) for label in item.get("labels") or ()]
        decision = str(item.get("decision") or "")
        if decision != "support_same_identity" or len(labels) < 2:
            unmapped.append(
                {
                    "file": filename,
                    "alias": " vs ".join(labels) or "(no labels)",
                    "reason": f"finding decision {decision!r} is not a label-scoped merge vote",
                }
            )
            continue
        # "BG:Borisov" / "BG:Borissov" -> the bare label is what the corpus holds.
        bare = [label.split(":", 1)[-1] for label in labels]
        add(
            {**item, "category": ""},
            alias=bare[0],
            canonical=bare[0],
            decision="merge",
        )

    return Ingested(reviews, proposed, unmapped, batch_id, provenance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="directory holding the eyeball json files")
    parser.add_argument("--run", default="", help="frozen run directory, used to resolve categories")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    directory = Path(args.dir)
    run_dir = Path(args.run) if args.run else None
    inventory = _category_inventory(run_dir)

    all_reviews: list[Review] = []
    all_proposed: list[RegistryEntry] = []
    unmapped: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []

    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_document(document, path.name, inventory)
        all_reviews.extend(parsed.reviews)
        all_proposed.extend(parsed.proposed)
        unmapped.extend(parsed.unmapped)
        summary.append(
            {
                "file": path.name,
                "batch_id": parsed.batch_id,
                "reviews": len(parsed.reviews),
                "proposed": len(parsed.proposed),
                "unmapped": len(parsed.unmapped),
                "provenance": parsed.provenance[:110],
            }
        )

    fresh: list[RegistryEntry] = []
    if not args.dry_run:
        ledger = Ledger.load(args.ledger) if Path(args.ledger).exists() else Ledger()
        if all_reviews:
            ledger.append(all_reviews, args.ledger)
        registry = Registry.load(args.registry) if Path(args.registry).exists() else Registry()
        fresh = [
            entry for entry in all_proposed if not registry.has_alias(entry.category, entry.alias)
        ]
        if fresh:
            registry.append(fresh, args.registry)

    report = {
        "files": summary,
        "reviews_recorded": len(all_reviews),
        "proposed_written": len(fresh),
        "unmapped": unmapped,
        "note": (
            "Single-pass reviews. They never satisfy the three-review rule on their own, and their "
            "provenance differs from the corpus batches, so the ledger reports such labels as mixed "
            "rather than complete."
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
