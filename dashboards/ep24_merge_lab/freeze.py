"""Freeze and hash the complete merge-lab input inventory (#311).

Why this exists
---------------
The merge lab already records a `manifest.json` per run, with a `sha256` for every input and output.
That manifest says what a run *read*. It does not say whether those files **still are** what the run
read, and it does not say how much review the labels in them actually oblige.

#311 begins by requiring exactly that: *"Freeze and hash the complete input inventory … Include
singletons and already merged clusters"*, because everything after it — three independent reviews per
label, a global reconciliation, a deployment — is only meaningful against a fixed input set.

This module produces that frozen artefact. It is deliberately read-only: it hashes, counts and
compares, and writes one JSON document. It merges nothing, decides nothing and never touches a source.

What "frozen" means here
------------------------
* every input and output of the named run is re-hashed from disk and compared to the digest the run
  recorded, so a file that changed after the run is *visible* rather than silently reviewed;
* the profile file is hashed and compared to the run's `profile_sha256`, because a changed profile
  means the rules that produced the clusters are no longer the rules being reviewed;
* the reviewable surface is counted per category, and the review obligation is stated as
  `labels × reviews_required` next to the reviews actually recorded (zero, until reviews exist);
* one `digest` covers the whole document, so two freezes that agree can be compared cheaply and two
  that disagree cannot be mistaken for each other.

A missing or changed file is reported, never repaired: a freeze that quietly tolerates a changed
input is worse than no freeze, because it certifies a corpus nobody can reconstruct.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import sources

SCHEMA = "laclaugpt.ep24_merge_lab.inventory.v1"

#: The issue asks for three independent reviews of every label; it is a property of the method, not a
#: setting, so it is a constant here rather than a flag someone can lower to make the work look done.
REVIEWS_REQUIRED = 3

#: Categories the review covers. Mirrors `model.CATEGORIES` but kept local so this module can be
#: imported by tests that do not want the merge engine.
CATEGORY_FILES = {
    "entity": "canonical_entity.csv",
    "person": "canonical_person.csv",
    "topic": "canonical_topic.csv",
    "theme": "canonical_theme.csv",
    "sentiment": "canonical_sentiment.csv",
}


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    """Deterministic bytes for hashing: sorted keys, no incidental whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _csv_rows(path: Path) -> int:
    """Data rows, excluding the header. A missing file is 0, and says so through `present`."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def _verify(entry: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Re-hash one recorded file and compare it with the digest the run recorded.

    `state` is one of:
      * ``verified`` — present, and the bytes are the bytes the run read;
      * ``changed``  — present, but a different digest: the run no longer describes this file;
      * ``missing``  — the run named it and it is not there;
      * ``unhashed`` — the run recorded no digest (older manifests), so nothing can be claimed.
    """
    record = dict(entry)
    path = Path(str(record.get("path") or ""))
    if not path.is_absolute():
        path = root / path
    record["resolved_path"] = str(path)
    if not path.exists():
        record["state"] = "missing"
        return record
    actual = sources.file_digest(path)
    record["actual_sha256"] = actual
    record["actual_bytes"] = path.stat().st_size
    recorded = str(record.get("sha256") or "")
    if not recorded:
        record["state"] = "unhashed"
    else:
        record["state"] = "verified" if actual == recorded else "changed"
    return record


def _category_rows(labels: Mapping[str, int], run_dir: Path) -> dict[str, dict[str, int]]:
    """Per category: how many labels entered, how they came out, how many still need a person."""
    alias_rows: dict[str, int] = {}
    alias_path = run_dir / "alias_map.csv"
    if alias_path.exists():
        import csv

        with alias_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                category = str(row.get("category") or "").strip()
                if category:
                    alias_rows[category] = alias_rows.get(category, 0) + 1

    report: dict[str, dict[str, int]] = {}
    for category in sorted(set(CATEGORY_FILES) | set(labels)):
        canonical = run_dir / CATEGORY_FILES.get(category, f"canonical_{category}.csv")
        review = run_dir / f"review_{category}.csv"
        entered = int(labels.get(category, 0))
        clusters = _csv_rows(canonical)
        queued = _csv_rows(review)
        report[category] = {
            "labels": entered,
            "clusters": clusters,
            "merged_aliases": alias_rows.get(category, 0),
            "queued_for_review": queued,
            # Singletons are labels that reached a cluster of their own. Counting them here keeps the
            # inventory honest about the part of the corpus no rule touched.
            "singletons": max(entered - alias_rows.get(category, 0), 0),
        }
    return report


def freeze(
    *,
    profile: Iterable[sources.Source],
    profile_path: Path | None,
    run_dir: Path,
    labels: Mapping[str, int] | None = None,
    frozen_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the frozen inventory document for one run.

    `labels` is the per-category distinct-label count from the pooled `sources.extract()`; pass it when the
    caller has already read the corpus, otherwise it is recomputed here. The recomputation reads the
    whole corpus, which is why the CLI prints it as slow rather than hiding it.

    Returns a JSON-serialisable document whose `digest` covers everything else.
    """
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    run_root = Path(str(manifest.get("root") or run_dir))

    if labels is None:
        # Count the pooled extraction, not the sum of per-source distinct counts.
        # This includes persons projected from entity codebooks and preserves polarity.
        labels = {category: len(stats) for category, stats in sources.extract(profile).items()}

    inputs = [_verify(entry, run_root) for entry in (manifest.get("inputs") or [])]
    outputs = []
    for name, entry in sorted((manifest.get("outputs") or {}).items()):
        record = dict(entry)
        record["path"] = str(run_dir / name)
        outputs.append(_verify(record, run_dir))

    profile_record: dict[str, Any] | None = None
    if profile_path is not None:
        profile_record = _verify(
            {
                "path": str(Path(profile_path)),
                "sha256": str(manifest.get("profile_sha256") or ""),
            },
            Path(str(Path(profile_path).parent)),
        )

    categories = _category_rows(labels, run_dir)
    labels_total = sum(entry["labels"] for entry in categories.values())

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "frozen_at": (frozen_at or datetime.now(UTC)).isoformat(),
        "run_id": str(manifest.get("run_id") or run_dir.name),
        "run_manifest_sha256": sources.file_digest(manifest_path) if manifest_path.exists() else "",
        "profile": profile_record,
        "inputs": inputs,
        "outputs": outputs,
        "categories": categories,
        "workload": {
            "labels_total": labels_total,
            "reviews_required_per_label": REVIEWS_REQUIRED,
            "reviews_required_total": labels_total * REVIEWS_REQUIRED,
            # Nothing in this repository can honestly claim a review, so the number starts at zero and
            # the acceptance bar is stated beside it rather than implied.
            "reviews_recorded": 0,
        },
        "integrity": {
            "inputs_verified": sum(1 for entry in inputs if entry["state"] == "verified"),
            "inputs_changed": [entry["path"] for entry in inputs if entry["state"] == "changed"],
            "inputs_missing": [entry["path"] for entry in inputs if entry["state"] == "missing"],
            "outputs_verified": sum(1 for entry in outputs if entry["state"] == "verified"),
            "frozen": bool(inputs) and all(entry["state"] == "verified" for entry in inputs + outputs)
            and (profile_record is None or profile_record["state"] == "verified"),
        },
    }
    # The digest identifies the *inventory*, not the moment it was taken: `frozen_at` is excluded so
    # that two freezes of unchanged inputs compare equal, and a re-freeze that differs is a real change
    # rather than a clock tick.
    identity = {key: value for key, value in document.items() if key != "frozen_at"}
    document["digest"] = _digest_bytes(_canonical_json(identity))
    return document


def write(document: Mapping[str, Any], path: Path) -> Path:
    """Write the frozen inventory as stable, human-readable JSON with a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def summarize(document: Mapping[str, Any]) -> str:
    """One line for a log or an issue comment: is it frozen, and how much review does it oblige?"""
    integrity = document.get("integrity") or {}
    workload = document.get("workload") or {}
    state = "frozen" if integrity.get("frozen") else "NOT frozen"
    changed = len(integrity.get("inputs_changed") or [])
    missing = len(integrity.get("inputs_missing") or [])
    parts = [f"inventory {state}: {workload.get('labels_total', 0)} labels"]
    if changed or missing:
        parts.append(f"{changed} changed, {missing} missing")
    parts.append(
        f"{workload.get('reviews_recorded', 0)}/{workload.get('reviews_required_total', 0)} reviews recorded"
    )
    parts.append(f"digest {str(document.get('digest') or '')[:12]}")
    return " | ".join(parts)
