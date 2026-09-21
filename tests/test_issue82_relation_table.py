from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.transforms import relations


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "document_id": "doc-1",
                "source_url": "https://example.invalid/source/1",
                "review_status": "PROVISIONAL",
                "relations": [
                    {
                        "source_ref": "actor",
                        "target_ref": "signifier",
                        "relation_type": "articulates",
                        "origin": "inferred",
                        "evidence_refs": ["ev-inferred"],
                    },
                    {
                        "source_ref": "signifier",
                        "target_ref": "topic",
                        "relation_type": "mentions",
                        "origin": "extracted",
                        "evidence_refs": "ev-extracted",
                    },
                    {
                        "source_ref": "researcher",
                        "target_ref": "formation",
                        "relation_type": "reviews",
                        "validation_status": "human-validated",
                        "evidence_refs": ["ev-reviewed"],
                    },
                    {
                        "source_ref": "",
                        "target_ref": "missing-source",
                        "evidence_refs": ["ev-malformed"],
                    },
                    {
                        "source_ref": "missing-target",
                        "target_ref": "",
                        "evidence_refs": ["ev-malformed"],
                    },
                    {
                        "source_ref": "no-evidence",
                        "target_ref": "hidden",
                    },
                    {
                        "source_ref": "bad-weight",
                        "target_ref": "safe-default",
                        "origin": "inferred",
                        "weight": {"not": "numeric"},
                        "evidence_refs": ["ev-weight"],
                    },
                ],
            },
            {
                "document_id": "doc-2",
                "source_url": "",
                "review_status": "ACCEPTED",
                "relations": [
                    {
                        "source_ref": "reviewed",
                        "target_ref": "but-untraceable",
                        "evidence_refs": ["ev-orphan"],
                    }
                ],
            },
        ]
    )


def test_canonical_relation_table_requires_source_and_evidence() -> None:
    table = relations(_frame(), require_evidence=True)

    assert set(table["source"]) == {"actor", "signifier", "researcher", "bad-weight"}
    assert table["source_url"].eq("https://example.invalid/source/1").all()
    assert table["evidence_refs"].map(bool).all()


def test_canonical_relation_table_normalizes_validation_statuses() -> None:
    table = relations(_frame(), require_evidence=True).set_index("source")

    assert table.loc["actor", "validation_status"] == "inferred"
    assert table.loc["signifier", "validation_status"] == "extracted"
    assert table.loc["researcher", "validation_status"] == "human-validated"
    assert table.loc["researcher", "edge_status"] == "human-validated"


def test_canonical_relation_table_drops_malformed_edges_and_handles_bad_weight() -> None:
    table = relations(_frame(), require_evidence=True).set_index("source")

    assert "missing-target" not in table.index
    assert "no-evidence" not in table.index
    assert table.loc["bad-weight", "weight"] == 1.0

def test_record_review_does_not_override_explicit_relation_origin() -> None:
    frame = pd.DataFrame(
        [
            {
                "document_id": "doc-reviewed",
                "source_url": "https://example.invalid/source/reviewed",
                "review_status": "ACCEPTED",
                "relations": [
                    {
                        "source_ref": "actor",
                        "target_ref": "claim",
                        "origin": "inferred",
                        "evidence_refs": ["ev-inferred"],
                    },
                    {
                        "source_ref": "actor",
                        "target_ref": "quote",
                        "origin": "extracted",
                        "evidence_refs": ["ev-extracted"],
                    },
                    {
                        "source_ref": "actor",
                        "target_ref": "unknown",
                        "evidence_refs": ["ev-record-review-only"],
                    },
                ],
            }
        ]
    )

    table = relations(frame, require_evidence=True).set_index("target")

    assert table.loc["claim", "validation_status"] == "inferred"
    assert table.loc["quote", "validation_status"] == "extracted"
    assert table.loc["unknown", "validation_status"] == "human-reviewed"

