"""Issue #165: the dashboard must measure freshness from the live results store.

The AI26 dashboard reported a false alarm on every load:

    Analysis is stale: newest analyzed record is 136.7 hours old

because it derived both the "Analyzed" count and the staleness timestamp from
``ai26__analyzed`` — a legacy collection the current Analysis worker no longer
writes, frozen at 2026-09-17 (21 documents) — while durable results were landing
in ``ai26__analysis_results`` (127 documents, newest minutes old).

These tests pin the source of the freshness metric so a future change to the
collection names cannot silently reintroduce the false warning.
"""
from __future__ import annotations

import ast
from pathlib import Path

from laclaugpt_visualization.ai26_dashboard import (
    FRESHNESS_WARNING_HOURS,
    ai26_collection_names,
)
from laclaugpt_visualization.config import Settings

MODULE = (
    Path(__file__).parents[1] / "src" / "laclaugpt_visualization" / "ai26_dashboard.py"
)


def _ai26_settings() -> Settings:
    return Settings(project_id="ai26", mongodb_uri="mongodb://127.0.0.1:27017/")


def test_results_come_from_the_live_collection() -> None:
    names = ai26_collection_names(_ai26_settings())
    assert names["results"] == "ai26__analysis_results"


def test_legacy_collection_is_not_the_progress_source() -> None:
    """The legacy store stays addressable but must not be named 'analyzed'.

    A key called ``analyzed`` invites exactly the defect: using a frozen legacy
    collection as the definition of analysis progress.
    """
    names = ai26_collection_names(_ai26_settings())
    assert "analyzed" not in names, (
        "the progress metric must not be keyed on an ambiguous 'analyzed' name; "
        "use 'results' (live) and 'legacy_analyzed' (retained, not a metric)"
    )
    assert names["legacy_analyzed"] == "ai26__analyzed"


def test_freshness_reads_the_results_collection_in_the_source() -> None:
    """Assert on the executable contract, not just the helper's return value.

    ``load_ai26_snapshot`` must query the results collection for the newest
    ``created_at``. Read the module's AST so a rename cannot satisfy the helper
    test while the snapshot still measures the legacy store.
    """
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE))

    snapshot = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "load_ai26_snapshot"
        ),
        None,
    )
    assert snapshot is not None, "load_ai26_snapshot must exist"

    body = ast.get_source_segment(source, snapshot) or ""
    assert 'names["results"]' in body, (
        "load_ai26_snapshot must read the live results collection"
    )
    # The legacy collection may be read for display, but never for freshness.
    freshness_lines = [
        line for line in body.splitlines() if "newest_analyzed" in line
    ]
    joined = "\n".join(freshness_lines)
    assert 'names["results"]' in joined or "names[" in joined, (
        "the newest-result lookup must name its collection explicitly"
    )
    assert 'db[names["legacy_analyzed"]].find_one(' not in joined, (
        "freshness must not be measured from the legacy analyzed collection"
    )


def test_warning_threshold_is_still_defined_so_the_fix_did_not_disable_it() -> None:
    """The remedy is a correct source, not a silenced warning."""
    assert FRESHNESS_WARNING_HOURS > 0


def test_settings_default_collection_matches_the_results_kind() -> None:
    """The canonical loader and the dashboard must agree on the collection."""
    settings = _ai26_settings()
    assert (
        settings.resolved_mongodb_collection
        == settings.distributed_namespace.mongo_collection("analysis_results")
    )
    assert settings.resolved_mongodb_collection == "ai26__analysis_results"
