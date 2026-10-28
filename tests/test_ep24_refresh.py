"""Tests for the EP24 dashboard freshness check (#210).

Synthetic manifests only: no database, no private data, no network. The point of the module is that
"is the dashboard current?" is a computed answer, so these tests pin the verdicts rather than the prose.
"""

from __future__ import annotations

import json

import pytest

from laclaugpt_visualization.ep24_refresh import (
    COUNTRIES,
    VERDICT_CURRENT,
    VERDICT_DIFFERENT_UNIT,
    VERDICT_INCOMPARABLE,
    VERDICT_STALE,
    RefreshError,
    annotate_manifest,
    compare,
    count_country_csvs,
    country_stats,
    load_manifest,
)


def manifest(*, records=100, per_country=33, unit="video", generated="2026-10-27T07:54:15+00:00",
             newest=None, include_countries=True):
    data = {
        "generated_at": generated,
        "record_unit": unit,
        "records": records,
        "countries": {},
    }
    if include_countries:
        for country in COUNTRIES:
            data["countries"][country] = {
                "records": per_country,
                "distinct_media": per_country,
                "source_documents": per_country + 10,
            }
    if newest:
        data["provenance"] = {c: {"newest_timestamp": newest.get(c)} for c in COUNTRIES}
    return data


class TestLoadManifest:
    def test_reads_a_directory(self, tmp_path):
        (tmp_path / "MANIFEST.json").write_text(json.dumps({"records": 1}), encoding="utf-8")
        assert load_manifest(tmp_path)["records"] == 1

    def test_missing_manifest_is_an_error(self, tmp_path):
        with pytest.raises(RefreshError):
            load_manifest(tmp_path)

    def test_malformed_json_is_an_error(self, tmp_path):
        (tmp_path / "MANIFEST.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(RefreshError):
            load_manifest(tmp_path)


class TestCountryStats:
    def test_reads_counts_and_provenance(self):
        stats = country_stats(manifest(per_country=7, newest={"finland": "2026-10-23T00:00:00+00:00"}))
        assert stats["finland"].records == 7
        assert stats["finland"].source_documents == 17
        assert stats["finland"].newest_timestamp == "2026-10-23T00:00:00+00:00"

    def test_missing_block_is_none(self):
        stats = country_stats(manifest(include_countries=False))
        assert all(stats[c] is None for c in COUNTRIES)


class TestVerdicts:
    def test_identical_manifests_are_current(self):
        report = compare(manifest(), manifest())
        assert report.verdict == VERDICT_CURRENT
        assert report.needs_refresh is False

    def test_a_newer_source_with_more_records_is_stale(self):
        report = compare(manifest(records=100, per_country=33),
                         manifest(records=120, per_country=40, generated="2026-10-28T00:00:00+00:00"))
        assert report.verdict == VERDICT_STALE
        assert report.needs_refresh is True
        assert any("more records" in r for r in report.reasons)

    def test_a_newer_timestamp_with_equal_counts_is_stale(self):
        dashboard = manifest(newest={"finland": "2026-10-20T00:00:00+00:00"})
        source = manifest(newest={"finland": "2026-10-23T00:00:00+00:00"})
        assert compare(dashboard, source).verdict == VERDICT_STALE

    def test_later_generation_with_equal_content_is_still_current(self):
        # Re-exporting unchanged data must not be reported as staleness.
        report = compare(manifest(generated="2026-10-26T00:00:00+00:00"),
                         manifest(generated="2026-10-27T00:00:00+00:00"))
        assert report.verdict == VERDICT_CURRENT
        assert any("content is current" in r for r in report.reasons)

    def test_different_record_units_are_not_a_defect(self):
        # The video-unit dashboard against an ingest-unit export: counts legitimately differ.
        report = compare(manifest(records=5306, unit="video"),
                         manifest(records=9999, unit="ingest"))
        assert report.verdict == VERDICT_DIFFERENT_UNIT
        assert report.needs_refresh is False
        assert any("record units differ" in r for r in report.reasons)

    def test_a_missing_country_is_incomparable(self):
        source = manifest()
        del source["countries"]["portugal"]
        report = compare(manifest(), source)
        assert report.verdict == VERDICT_INCOMPARABLE
        assert any("portugal" in r for r in report.reasons)

    def test_a_zero_record_country_is_incomparable(self):
        source = manifest()
        source["countries"]["poland"]["records"] = 0
        report = compare(manifest(), source)
        assert report.verdict == VERDICT_INCOMPARABLE
        assert any("zero" in r for r in report.reasons)

    def test_a_totals_only_dashboard_falls_back_to_totals(self):
        # The streaming export writes no countries block; that must not read as "incomparable".
        dashboard = manifest(records=500, include_countries=False)
        source = manifest(records=500, per_country=166)
        report = compare(dashboard, source)
        assert report.verdict == VERDICT_CURRENT
        assert any("totals-only" in r for r in report.reasons)

    def test_a_totals_only_dashboard_goes_stale_on_a_bigger_source(self):
        dashboard = manifest(records=500, include_countries=False)
        source = manifest(records=620, per_country=206)
        assert compare(dashboard, source).verdict == VERDICT_STALE

    def test_a_dashboard_holding_more_records_is_not_stale(self):
        # 5,306 (streaming rule) vs 4,866 (mongo media-key rule) is an identity difference, not rot.
        dashboard = manifest(records=5306, include_countries=False)
        source = manifest(records=4866, per_country=1622)
        report = compare(dashboard, source)
        assert report.verdict == VERDICT_CURRENT
        assert any("identity-rule difference" in r for r in report.reasons)

    def test_report_serialises(self):
        payload = compare(manifest(), manifest()).as_dict()
        assert payload["verdict"] == VERDICT_CURRENT
        assert set(payload["per_country"]) == set(COUNTRIES)


class TestCountryCounts:
    def test_counts_rows_without_the_header(self, tmp_path):
        (tmp_path / "finland.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        (tmp_path / "poland.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        assert count_country_csvs(tmp_path) == {"finland": 2, "poland": 1}

    def test_a_missing_country_is_absent_not_zero(self, tmp_path):
        (tmp_path / "finland.csv").write_text("a\n1\n", encoding="utf-8")
        assert "portugal" not in count_country_csvs(tmp_path)

    def test_annotation_refuses_a_mismatched_total(self, tmp_path):
        (tmp_path / "finland.csv").write_text("a\n1\n2\n", encoding="utf-8")
        (tmp_path / "MANIFEST.json").write_text(json.dumps({"records": 99}), encoding="utf-8")
        with pytest.raises(RefreshError):
            annotate_manifest(tmp_path)

    def test_annotation_writes_the_block(self, tmp_path):
        (tmp_path / "finland.csv").write_text("a\n1\n2\n", encoding="utf-8")
        (tmp_path / "MANIFEST.json").write_text(json.dumps({"records": 2}), encoding="utf-8")
        manifest = annotate_manifest(tmp_path)
        assert manifest["countries"] == {"finland": {"records": 2}}
        assert load_manifest(tmp_path)["countries"]["finland"]["records"] == 2
