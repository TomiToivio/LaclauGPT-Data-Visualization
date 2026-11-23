"""Audit the PLEDGE label merge: what still means the same thing but is counted twice?

Run against the workbook (not against the merge map — that would be circular):

    python tools/audit_pledge_labels.py path/to/ep24_pledge_clean_v2.csv

It groups tokens by an *aggressive* key — accents, case, punctuation and **all** parentheses
removed — and reports the groups that still hold more than one token after merging. A group there
is not automatically a bug: ``government`` / ``government (france)`` are different governments. The
output is a judgement queue, and the headline is the share of occurrences behind a parenthesis,
which is the class a rule cannot decide on its own.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboards" / "pledge"))
import pledge_entities as pe

DEFAULT_CSV = Path("/home/tomi/work/LaclauGPT-Private/analysis/pledge/ep24_pledge_clean_v2.csv")
COLUMNS = ("entities", "topics", "persons", "themes")


def aggressive_key(label: str) -> str:
    text = unicodedata.normalize("NFKD", str(label))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = text.replace("&", " ").replace("/", " ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"^the ", "", re.sub(r"\s+", " ", text).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--show", type=int, default=8, help="groups to print per column")
    args = parser.parse_args()

    frame = pd.read_csv(args.csv, low_memory=False)
    for column in COLUMNS:
        forms = pe.build_forms(frame[column])
        merged = frame[column].map(lambda value, f=forms: pe.merge_cell(value, f))
        after: collections.Counter[str] = collections.Counter()
        for value in merged:
            after.update(pe.split_cell(value))

        groups: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
        for label, count in after.items():
            groups[aggressive_key(label)].append((label, count))
        left = {key: members for key, members in groups.items() if len(members) > 1}
        parenthetical = sum(count for members in left.values() for label, count in members if "(" in label)
        total = sum(after.values())

        print(
            f"{column}: {len(after)} tokens | groups needing judgement {len(left)} | "
            f"occurrences behind a parenthesis {parenthetical}/{total} = {parenthetical * 100 / total:.2f}%"
        )
        for key, members in sorted(left.items(), key=lambda item: -sum(c for _, c in item[1]))[: args.show]:
            shown = ", ".join(f"{label!r}x{count}" for label, count in sorted(members, key=lambda m: -m[1])[:3])
            print(f"    {key}: {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
