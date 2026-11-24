"""Freeze one review batch into LaclauGPT-Private so every reviewer sees the same snapshot (#311).

A batch is frozen before any agent looks at it: same file, same hash, same labels. Without that, three
"independent" reviews are three reviews of three different things.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "dashboards"))

#: The labels this batch covers: the highest-impact contested items across all five categories.
PICKS = [
    ("entity", "politician"),
    ("entity", "political parties"),
    ("entity", "speaker"),
    ("person", "jean-marie le pen"),
    ("sentiment", "european union"),
    ("sentiment", "hungarian people"),
    ("theme", "elections"),
    ("theme", "eu policies"),
    ("topic", "european parliament elections"),
    ("topic", "social contract"),
]


def main(run_dir: Path, out_path: Path, batch_id: str = "batch-0001") -> Path:
    items = []
    for category, label in PICKS:
        path = run_dir / f"review_{category}.csv"
        row = None
        if path.exists():
            for candidate in csv.DictReader(path.open(encoding="utf-8", newline="")):
                if candidate["label"] == label:
                    row = candidate
                    break
        items.append(
            {
                "label_id": f"{category}:{label}",
                "category": category,
                "label": label,
                "occurrences": int(row["occurrences"]) if row else None,
                "machine_alternatives": (row["alternatives"] if row else ""),
                "machine_reason": (row["reason"] if row else ""),
                "decision_required": "merge | keep_separate",
            }
        )

    payload = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run": run_dir.name,
        "instructions": (
            "Decide, per label, whether it has an exact canonical equivalent and under which English "
            "Wikipedia title. Cite the URL you actually read. If no exact article exists, say so and "
            "propose a concise English label preserving specific meaning. Never merge merely related "
            "concepts, distinct people or opposing sentiments."
        ),
        "items": items,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    out_path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    (out_path.parent / f"{batch_id}.sha256").write_text(f"{digest}  {out_path.name}\n", encoding="utf-8")
    print(f"{out_path}  sha256={digest[:16]}  items={len(items)}")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("out")
    parser.add_argument("--batch-id", default="batch-0001")
    args = parser.parse_args()
    main(Path(args.run_dir), Path(args.out), args.batch_id)
