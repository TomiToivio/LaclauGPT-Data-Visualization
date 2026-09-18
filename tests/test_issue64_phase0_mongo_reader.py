from datetime import datetime, timezone

import pytest

from laclaugpt_visualization.phase0_mongo import (
    Phase0ConfigError,
    Phase0Filters,
    Phase0MongoConfig,
    Phase0MongoReader,
    normalize_phase0_record,
)


class FakeCursor(list):
    def limit(self, value):
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def find(self, query, projection):
        self.calls.append((query, projection))
        return FakeCursor(self.records)


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        self.collection.requested_name = name
        return self.collection


class FakeClient:
    def __init__(self, collection):
        self.database = FakeDatabase(collection)

    def __getitem__(self, name):
        self.database.requested_name = name
        return self.database


def test_phase0_config_uses_shared_contract_and_collection_name():
    config = Phase0MongoConfig.from_env(
        {
            "LACLAUGPT_MONGODB_URI": "mongodb://example",
            "LACLAUGPT_MONGODB_DATABASE": "laclaugpt",
            "LACLAUGPT_PROJECT_ID": "ai26",
        }
    )
    assert config.collection_name == "laclaugpt2_ai26_scraper_collection"


def test_phase0_config_missing_values_fail_clearly():
    with pytest.raises(Phase0ConfigError, match="LACLAUGPT_MONGODB_DATABASE"):
        Phase0MongoConfig.from_env(
            {
                "LACLAUGPT_MONGODB_URI": "mongodb://example",
                "LACLAUGPT_PROJECT_ID": "ai26",
            }
        )


def test_query_construction_is_bounded_and_simple():
    query = Phase0Filters(
        status="analyzed",
        start_date="2026-09-01",
        end_date=datetime(2026, 9, 18, tzinfo=timezone.utc),
        actor="OpenAI",
        arena="labs",
        ai_formation="accelerationist",
        language="en",
    ).to_query()

    assert query["phase0.discourse.status"] == "ok"
    assert query["source_date"]["$gte"] == datetime(2026, 9, 1)
    assert query["actor_name"] == "OpenAI"
    assert query["arena"] == "labs"
    assert query["ai_formation"] == "accelerationist"
    assert query["language"] == "en"


def test_awaiting_analysis_query_distinguishes_missing_analysis():
    query = Phase0Filters(status="awaiting-analysis").to_query()
    assert "$or" in query
    assert {"phase0.discourse": {"$exists": False}} in query["$or"]


def test_normalization_uses_source_url_identity_and_statuses():
    analyzed = normalize_phase0_record(
        {
            "_id": "mongo-only",
            "source_url": "https://example.test/a",
            "phase0": {"discourse": {"status": "ok"}, "summary": {"status": "ok"}},
        }
    )
    awaiting = normalize_phase0_record({"source_url": "https://example.test/b"})
    error = normalize_phase0_record(
        {
            "source_url": "https://example.test/c",
            "phase0": {"discourse": {"status": "error", "error": "boom"}},
        }
    )

    assert analyzed["source_url"] == "https://example.test/a"
    assert "_id" not in analyzed
    assert analyzed["analysis_status"] == "analyzed"
    assert awaiting["analysis_status"] == "awaiting-analysis"
    assert error["analysis_status"] == "error"
    assert error["phase0"]["discourse"]["error"] == "boom"


def test_reader_targets_phase0_collection_without_live_mongodb():
    collection = FakeCollection(
        [{"source_url": "https://example.test/a", "phase0": {"discourse": {"status": "ok"}}}]
    )
    client = FakeClient(collection)
    reader = Phase0MongoReader(
        Phase0MongoConfig("mongodb://unused", "laclaugpt", "ai26"),
        client=client,
    )

    records = reader.find(Phase0Filters(status="analyzed"), limit=25)

    assert client.database.requested_name == "laclaugpt"
    assert collection.requested_name == "laclaugpt2_ai26_scraper_collection"
    assert collection.calls == [
        ({"phase0.discourse.status": "ok"}, {"_id": False})
    ]
    assert records[0]["analysis_status"] == "analyzed"


@pytest.mark.parametrize("limit", [0, 501])
def test_reader_enforces_bounded_limit(limit):
    reader = Phase0MongoReader(
        Phase0MongoConfig("mongodb://unused", "laclaugpt", "ai26"),
        client=FakeClient(FakeCollection([])),
    )
    with pytest.raises(ValueError, match="limit must be between"):
        reader.find(limit=limit)
