from __future__ import annotations

import sqlite3

import pandas as pd

from laclaugpt_visualization.ep24 import (
    country_counts,
    dimension_counts,
    legacy_change_summary,
    load_ep24_bundle,
    normalize_ep24_frame,
    overview,
    qa_summary,
)


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_url": "synthetic://fi/1",
                "schema_version": "1.0",
                "source_country": "Finland",
                "source_language": "fi",
                "analysis_status": "analyzed",
                "entities": '["Actor FI"]',
                "topics": '["Labour"]',
                "signifiers": '["turvallisuus"]',
                "nodal_points": '["kansa"]',
                "frontier": '["elite"]',
                "affects": '["hope"]',
                "codebook_refs": '["ep24-fi"]',
                "uncertainties": "[]",
            },
            {
                "source_url": "synthetic://pl/1",
                "schema_version": "1.0",
                "source_country": "Poland",
                "source_language": "pl",
                "analysis_status": "analyzed",
                "entities": '["Actor PL"]',
                "topics": '["Labour"]',
                "signifiers": '["bezpieczeństwo"]',
                "nodal_points": '["naród"]',
                "frontier": '["elita"]',
                "affects": '["anger"]',
                "codebook_refs": '["ep24-pl"]',
                "uncertainties": '["ambiguous frontier"]',
            },
        ]
    )


def test_ep24_bundle_prefers_combined_csv_and_loads_companions(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _rows().to_csv(data / "combined.csv", index=False)
    _rows().iloc[:1].to_csv(data / "finland.csv", index=False)
    _rows().iloc[1:].to_csv(data / "poland.csv", index=False)
    pd.DataFrame([{"change_type": "added"}, {"change_type": "unchanged"}]).to_csv(
        data / "legacy_comparison.csv", index=False
    )
    pd.DataFrame([{"source_url": "synthetic://bad", "stage": "analysis"}]).to_csv(
        data / "failures.csv", index=False
    )

    bundle = load_ep24_bundle(tmp_path)

    assert bundle.storage_kind == "csv"
    assert bundle.source_path == data / "combined.csv"
    assert set(bundle.records["source_country"]) == {"Finland", "Poland"}
    assert len(bundle.legacy_comparison) == 2
    assert len(bundle.failures) == 1


def test_ep24_bundle_falls_back_to_sqlite_records_table(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "ep24.sqlite3"
    with sqlite3.connect(path) as connection:
        _rows().to_sql("records", connection, index=False)

    bundle = load_ep24_bundle(tmp_path)

    assert bundle.storage_kind == "sqlite"
    assert bundle.source_path == path
    assert set(bundle.records["source_country"]) == {"Finland", "Poland"}


def test_ep24_country_and_dimension_views_preserve_national_identity() -> None:
    frame = load_ep24_bundle_from_frame(_rows())
    counts = country_counts(frame)
    signifiers = dimension_counts(frame, "signifiers")
    topics = dimension_counts(frame, "topics")

    assert counts.set_index("country")["documents"].to_dict() == {"Finland": 1, "Poland": 1}
    assert set(signifiers["country"]) == {"Finland", "Poland"}
    assert set(signifiers["signifiers"]) == {"turvallisuus", "bezpieczeństwo"}
    assert set(topics["topics"]) == {"Labour"}
    assert len(topics) == 2


def load_ep24_bundle_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return normalize_ep24_frame(frame)


def test_ep24_overview_qa_and_legacy_summary_are_descriptive() -> None:
    frame = load_ep24_bundle_from_frame(_rows())
    failures = pd.DataFrame([{"stage": "parse"}])
    values = overview(frame, failures)

    assert values["documents"] == 2
    assert values["finland"] == 1
    assert values["poland"] == 1
    assert values["analyzed"] == 2
    assert values["failures"] == 1

    qa = qa_summary(frame, failures).set_index("metric")["value"].to_dict()
    assert qa["records"] == 2
    assert qa["missing_source_url"] == 0
    assert qa["failure_rows"] == 1
    assert qa["records_with_uncertainty"] == 1

    comparison = pd.DataFrame(
        [{"change_type": "added"}, {"change_type": "added"}, {"change_type": "removed"}]
    )
    summary = legacy_change_summary(comparison).set_index("change")["count"].to_dict()
    assert summary == {"added": 2, "removed": 1}
