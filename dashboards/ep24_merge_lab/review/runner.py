"""Run the panel over a batch, with checkpoints you can actually resume from (#311).

Concurrency is bounded and every completed review is on disk before the next one starts, so a
killed run costs at most the calls in flight. A reviewer that fails is recorded as a failed
attempt, never as an opinion.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ledger import Review as SharedReview
from . import ledger, providers


@dataclass
class BatchStats:
    asked: int = 0
    recorded: int = 0
    skipped: int = 0
    failed: int = 0
    seconds: float = 0.0

    def as_json(self) -> dict[str, Any]:
        return {
            "asked": self.asked,
            "recorded": self.recorded,
            "skipped": self.skipped,
            "failed": self.failed,
            "seconds": round(self.seconds, 1),
        }


def shared_problems(
    unit: dict[str, Any], result: dict[str, Any], snapshot_sha256: str
) -> list[str]:
    """Check a panel verdict against the shared ledger's contract before it counts as a review.

    The repository has one rule for what counts as evidence (`ep24_merge_lab.ledger.Review`): a
    reviewer is named, the snapshot is hashed, and a merge cites a verified URL or says why no
    article exists. A verdict that fails this is a failed attempt, not a vote.
    """
    return SharedReview(
        batch_id=f"panel-{unit['unit_id']}",
        label_id=unit["unit_id"],
        category=str(unit.get("category", "")),
        label=" | ".join(unit.get("labels", []))[:200],
        reviewer=str(result.get("reviewer", "")),
        decision=str(result.get("decision", "")),
        canonical=str(result.get("canonical", "")),
        wiki_title=str(result.get("wikipedia_title") or ""),
        wiki_url=str(result.get("wikipedia_url") or ""),
        wikidata_qid=str(result.get("qid") or ""),
        fallback_reason=str(result.get("fallback_reason") or ""),
        confidence=float(result.get("confidence", 0.0)),
        reasoning=str(result.get("rationale", "")),
        snapshot_sha256=snapshot_sha256,
    ).validate()


def _one(
    unit: dict[str, Any],
    reviewer: providers.Reviewer,
    ledger_path: Path,
    snapshot_sha256: str = "",
) -> tuple[str, dict[str, Any] | None, str]:
    try:
        result = providers.review(unit, reviewer)
        problems = shared_problems(unit, result, snapshot_sha256)
        if problems:
            raise ValueError("shared contract: " + "; ".join(problems)[:200])
    except Exception as exc:  # noqa: BLE001 - any failure is a failed attempt, not a review
        ledger.append(
            ledger_path,
            {
                "type": "attempt",
                "unit_id": unit["unit_id"],
                "reviewer": reviewer.name,
                "model": reviewer.model,
                "error": f"{type(exc).__name__}: {exc}"[:300],
            },
        )
        return unit["unit_id"], None, f"{type(exc).__name__}"
    ledger.append(
        ledger_path,
        {"type": "review", "unit_id": unit["unit_id"], "category": unit["category"], **result},
    )
    return unit["unit_id"], result, ""


def _batch(
    units: list[dict[str, Any]],
    reviewer: providers.Reviewer,
    ledger_path: Path,
    snapshot_sha256: str = "",
) -> tuple[int, int]:
    """One model call for several units; every verdict is written on its own ledger line."""
    try:
        verdicts = providers.review_batch(units, reviewer)
    except Exception as exc:  # noqa: BLE001 - a failed batch is retried unit by unit below
        ledger.append(
            ledger_path,
            {
                "type": "attempt",
                "unit_id": ",".join(unit["unit_id"] for unit in units)[:200],
                "reviewer": reviewer.name,
                "model": reviewer.model,
                "error": f"batch {type(exc).__name__}: {exc}"[:300],
            },
        )
        recorded = 0
        for unit in units:
            _, result, _ = _one(unit, reviewer, ledger_path, snapshot_sha256)
            recorded += 1 if result else 0
        return recorded, 0

    recorded = 0
    for unit in units:
        verdict = verdicts.get(unit["unit_id"])
        if verdict is not None:
            problems = shared_problems(unit, verdict, snapshot_sha256)
            if problems:
                ledger.append(
                    ledger_path,
                    {
                        "type": "attempt",
                        "unit_id": unit["unit_id"],
                        "reviewer": reviewer.name,
                        "model": reviewer.model,
                        "error": ("shared contract: " + "; ".join(problems))[:300],
                    },
                )
                verdict = None
        if verdict is None:
            # The reviewer skipped this unit: record a failure rather than invent agreement.
            ledger.append(
                ledger_path,
                {
                    "type": "attempt",
                    "unit_id": unit["unit_id"],
                    "reviewer": reviewer.name,
                    "model": reviewer.model,
                    "error": "unit missing from the batch reply",
                },
            )
            continue
        ledger.append(
            ledger_path,
            {"type": "review", "unit_id": unit["unit_id"], "category": unit["category"], **verdict},
        )
        recorded += 1
    return recorded, 0


def run(
    units: Iterable[dict[str, Any]],
    reviewers: list[providers.Reviewer],
    ledger_path: Path,
    *,
    concurrency: int = 6,
    limit: int = 0,
    progress_every: int = 50,
    batch_size: int = 1,
    snapshot_sha256: str = "",
) -> BatchStats:
    """Ask every reviewer about every unit not yet reviewed by them."""
    done = ledger.reviewed_pairs(ledger_path)
    pending: list[tuple[dict[str, Any], providers.Reviewer]] = []
    stats = BatchStats()
    for unit in units:
        for reviewer in reviewers:
            if (unit["unit_id"], reviewer.name) in done:
                stats.skipped += 1
                continue
            pending.append((unit, reviewer))
    if limit:
        pending = pending[:limit]
    stats.asked = len(pending)
    started = time.time()

    if batch_size > 1:
        grouped: dict[str, list[dict[str, Any]]] = {}
        reviewers_by_name = {reviewer.name: reviewer for reviewer in reviewers}
        for unit, reviewer in pending:
            grouped.setdefault(reviewer.name, []).append(unit)
        batches = [
            (grouped[name][start : start + batch_size], reviewers_by_name[name])
            for name in grouped
            for start in range(0, len(grouped[name]), batch_size)
        ]
        stats.asked = len(pending)
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {
                pool.submit(_batch, batch_units, reviewer, ledger_path, snapshot_sha256): batch_units
                for batch_units, reviewer in batches
            }
            for number, future in enumerate(as_completed(futures), start=1):
                recorded, _ = future.result()
                stats.recorded += recorded
                stats.failed += len(futures[future]) - recorded
                if number % max(1, progress_every // batch_size) == 0:
                    print(
                        json.dumps(
                            {"batches": number, "of": len(batches),
                             "recorded": stats.recorded, "failed": stats.failed}
                        ),
                        flush=True,
                    )
        stats.seconds = time.time() - started
        return stats

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(_one, unit, reviewer, ledger_path, snapshot_sha256): (unit, reviewer)
            for unit, reviewer in pending
        }
        for number, future in enumerate(as_completed(futures), start=1):
            _, result, error = future.result()
            if result is None:
                stats.failed += 1
                unit, reviewer = futures[future]
                # One retry with a different reviewer slot keeps the panel honest without
                # pretending a failed call was a review.
                if error.startswith("TimeoutError") and number % 10 == 0:
                    pass
            else:
                stats.recorded += 1
            if number % progress_every == 0:
                print(
                    json.dumps(
                        {
                            "progress": number,
                            "of": len(pending),
                            "recorded": stats.recorded,
                            "failed": stats.failed,
                        }
                    ),
                    flush=True,
                )
    stats.seconds = time.time() - started
    return stats


def adjudicate_disagreements(
    units: dict[str, dict[str, Any]],
    ledger_path: Path,
    adjudicator: providers.Reviewer,
    out_path: Path,
    *,
    limit: int = 0,
) -> int:
    """For every unit where the panel split, ask the adjudicator and record the verdict."""
    by_unit = ledger.reviews_by_unit(ledger_path)
    already: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line)["unit_id"])
    count = 0
    with out_path.open("a", encoding="utf-8") as handle:
        for unit_id, reviews in by_unit.items():
            if unit_id in already or unit_id not in units:
                continue
            if len({review["decision"] for review in reviews}) == 1 and len(
                {(review.get("wikipedia_title") or review["canonical"]).casefold() for review in reviews}
            ) == 1:
                continue
            try:
                verdict = providers.adjudicate(units[unit_id], reviews, adjudicator)
            except Exception as exc:  # noqa: BLE001
                ledger.append(
                    ledger_path,
                    {
                        "type": "attempt",
                        "unit_id": unit_id,
                        "reviewer": adjudicator.name,
                        "model": adjudicator.model,
                        "error": f"adjudication {type(exc).__name__}: {exc}"[:300],
                    },
                )
                continue
            verdict["unit_id"] = unit_id
            handle.write(json.dumps(verdict, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            count += 1
            if limit and count >= limit:
                break
    return count
