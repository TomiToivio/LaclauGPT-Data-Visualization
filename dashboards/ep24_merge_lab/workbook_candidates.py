"""Build protected human-grounded candidate groups before automatic matching (#311).

The coverage audit supplies raw aliases and workbook row provenance. This plan is
not an approved registry: it separates verified candidates from matcher-only
labels and quarantines conflicts rather than letting similarity join them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .workbook_coverage import audit


def build_plan(coverage: dict) -> dict:
    categories = {}
    for category, report in sorted(coverage["categories"].items()):
        evidence = coverage["workbook_evidence"]["sources"][category]
        provenance = defaultdict(list)
        for pair in evidence["pairs"]:
            provenance[(pair["alias"], pair["canonical"])].append(
                {"sheet": pair["sheet"], "row": pair["row"]}
            )
        groups = defaultdict(set)
        for match in report["matched"]:
            groups[match["canonical"]].add(match["alias"])
        conflicts = set(report["conflicting"])
        # A target that is itself mapped elsewhere is not a safe terminal label.
        outgoing = defaultdict(set)
        for pair in evidence["pairs"]:
            outgoing[pair["alias"].strip().casefold()].add(pair["canonical"])
        protected = []
        quarantined = []
        for canonical, aliases in sorted(groups.items()):
            key = canonical.strip().casefold()
            target_conflict = key in evidence["conflicts"] or any(
                value != canonical for value in outgoing.get(key, set())
            )
            item = {
                "category": category,
                "canonical": canonical,
                "aliases": sorted(aliases),
                "workbook_sha256": evidence["sha256"],
                "provenance": [
                    {"alias": alias, "rows": provenance[(alias, canonical)]}
                    for alias in sorted(aliases)
                ],
                "status": "proposed",
            }
            if target_conflict or any(alias in conflicts for alias in aliases):
                item["reason"] = "conflicting or chained workbook target"
                quarantined.append(item)
            else:
                protected.append(item)
        # Never send workbook targets or their case variants to automatic matching.
        reserved = {
            value.strip().casefold()
            for pair in evidence["pairs"]
            for value in (pair["alias"], pair["canonical"])
        }
        matcher = []
        reserved_unmatched = []
        for alias in report["unmatched"]:
            if alias.strip().casefold() in reserved:
                reserved_unmatched.append(alias)
            else:
                matcher.append(alias)
        categories[category] = {
            "protected_candidates": protected,
            "quarantined_candidates": quarantined,
            "conflicting_aliases": sorted(conflicts),
            "reserved_unmatched": sorted(reserved_unmatched),
            "matcher_only": sorted(matcher),
            "counts": {
                "protected_aliases": sum(len(item["aliases"]) for item in protected),
                "quarantined_aliases": sum(len(item["aliases"]) for item in quarantined),
                "conflicting_aliases": len(conflicts),
                "reserved_unmatched": len(reserved_unmatched),
                "matcher_only": len(matcher),
                "observed": report["counts"]["observed"],
            },
        }
    payload = {
        "schema": "ep24.workbook_candidate_plan/1",
        "inputs": coverage["inputs"],
        "categories": categories,
        "activation_authorized": False,
    }
    payload["digest"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "root", "workbooks", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = build_plan(audit(args.profile, args.root, args.workbooks))
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
