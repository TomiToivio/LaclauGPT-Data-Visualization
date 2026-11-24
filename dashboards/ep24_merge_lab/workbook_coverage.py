"""Read-only exact workbook coverage audit before label normalization (#311).

Run on an authorized hydrated checkout. Never activates or mutates a merge.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from . import sources
from .workbook_evidence import inspect_workbooks


def audit(profile: Path, root: Path, workbooks: Path) -> dict:
    evidence = inspect_workbooks(workbooks)
    observed = defaultdict(set)
    inputs = []
    for source in sources.load_profile(profile, root=root):
        with source.path.open("rb") as handle:
            if handle.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError(f"{source.name}: hydrate Git LFS first")
        before = sources.file_digest(source.path)
        if source.kind == "records":
            extracted = [sources.read_records(source)]
        elif source.kind == "entity_codebook":
            extracted = [sources.read_codebook(source, category=c) for c in ("entity", "person")]
        elif source.kind == "topic_codebook":
            extracted = [sources.read_codebook(source, category="topic")]
        else:
            raise ValueError(f"Unknown source kind: {source.kind}")
        if sources.file_digest(source.path) != before:
            raise ValueError(f"{source.name}: source changed during audit")
        inputs.append({"source": source.name, "sha256": before})
        for item in extracted:
            for category, stats in item.stats.items():
                observed[category].update(stat.label for stat in stats.values())
    reports = {}
    for category, source in evidence["sources"].items():
        index = defaultdict(set)
        for pair in source["pairs"]:
            index[pair["alias"]].add(pair["canonical"])
        matched, unmatched, conflicts = [], [], []
        for alias in sorted(observed[category]):
            targets = index.get(alias, set())
            if len(targets) > 1 or alias.strip().casefold() in source["conflicts"]:
                conflicts.append(alias)
            elif targets:
                matched.append({"alias": alias, "canonical": next(iter(targets))})
            else:
                unmatched.append(alias)
        reports[category] = {
            "matched": matched, "unmatched": unmatched, "conflicting": conflicts,
            "unused_workbook_aliases": sorted(set(index) - observed[category]),
            "counts": {"matched": len(matched), "unmatched": len(unmatched),
                       "conflicting": len(conflicts), "observed": len(observed[category])},
        }
    return {"schema": "ep24.workbook_coverage/1", "inputs": inputs,
            "workbook_evidence": evidence, "categories": reports,
            "activation_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "root", "workbooks", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.profile, args.root, args.workbooks)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
