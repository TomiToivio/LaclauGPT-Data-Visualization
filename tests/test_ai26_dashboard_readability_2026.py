"""AI26 private dashboard reliability and readability regressions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from laclaugpt_visualization import ai26_dashboard
from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.data import filter_frame, normalize_frame


def test_ai26_text_only_distributed_profile_does_not_need_s3():
    cfg = Settings(
        _env_file=None, project_id="ai26", profile="server", machine="linux-server",
        execution="web-service", storage="distributed", storage_backend="mongodb",
        data_backend="mongodb", cache_backend="redis", object_backend="local",
        messaging_backend="redis", mongodb_uri="mongodb://example.invalid",
        redis_url="redis://example.invalid",
    )
    cfg.validate_remote_requirements()


def test_close_read_handles_missing_and_nested_values():
    assert ai26_dashboard._readable_text(pd.NA) == "Not available"
    assert ai26_dashboard._readable_text(float("nan"), "") == ""
    assert ai26_dashboard._readable_text({"a": 1}) == '{"a": 1}'
    assert ai26_dashboard._readable_text([], "") == "[]"


def test_timestamp_parser_handles_bson_epoch_and_invalid_data():
    dt = datetime(2026, 11, 22, 12, tzinfo=UTC)
    assert ai26_dashboard._as_utc_timestamp(dt) == dt
    assert ai26_dashboard._as_utc_timestamp(dt.timestamp()) == dt
    assert ai26_dashboard._as_utc_timestamp("2026-11-22T12:00:00Z") == dt
    assert ai26_dashboard._as_utc_timestamp("invalid") is None
    assert ai26_dashboard._as_utc_timestamp(float("nan")) is None


def test_literal_search_accepts_regex_metacharacters():
    frame = normalize_frame(pd.DataFrame([
        {"source_url": "synthetic://one", "summary": "AI [policy]"},
        {"source_url": "synthetic://two", "summary": "AI governance"},
    ]))
    assert filter_frame(frame, query="[policy]")["source_url"].tolist() == ["synthetic://one"]


def test_freshness_chooses_latest_from_mixed_epoch_and_datetime(monkeypatch):
    older = datetime.now(UTC) - timedelta(hours=12)
    recent_epoch = (datetime.now(UTC) - timedelta(minutes=30)).timestamp()

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def sort(self, *args, **kwargs):
            return self

        def limit(self, number):
            return self.rows[:number]

    class Collection:
        def __init__(self, name):
            self.name = name

        def find(self, query):
            assert query == {"project_id": "ai26"}
            if self.name == "ai26__analysis_results":
                return Cursor([
                    {"source_url": "synthetic://one", "created_at": recent_epoch},
                    {"source_url": "synthetic://two", "created_at": older},
                ])
            return Cursor([])

        def count_documents(self, query):
            return 2 if self.name == "ai26__analysis_results" else 0

        def find_one(self, query, *, sort, projection):
            # BSON descending order can return a dated BSON row over newer epoch floats.
            return {"created_at": older}

    class DB:
        def __getitem__(self, name):
            return Collection(name)

    class Client:
        def __getitem__(self, name):
            return DB()

        def close(self):
            pass

    monkeypatch.setattr(ai26_dashboard, "_mongo_client", lambda _: Client())
    cfg = Settings(_env_file=None, project_id="ai26", mongodb_uri="mongodb://example.invalid")
    snapshot = ai26_dashboard.load_ai26_snapshot(cfg)
    assert snapshot.counts["analyzed"] == 2
    assert snapshot.analyzed_age_hours is not None
    assert snapshot.analyzed_age_hours < 1
    assert snapshot.newest_analyzed_at is not None


def test_ranked_bar_is_readable_and_bounded():
    data = pd.DataFrame({"formations": ["A", "B", "C"], "count": [10, 5, 2]})
    figure = ai26_dashboard._ranked_bar(data, "formations", "Formations")
    assert figure.layout.height >= 280
    assert list(figure.data[0].y) == ["C", "B", "A"]
    assert [int(value) for value in figure.data[0].text] == [2, 5, 10]
