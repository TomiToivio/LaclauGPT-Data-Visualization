from __future__ import annotations

from contextlib import nullcontext

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.phase0_browser import (
    PHASE0_BROWSER_MAX_LIMIT,
    Phase0BrowserConfigurationError,
    load_phase0_browser_records,
    phase0_browser_state,
    phase0_collection_name,
    render_phase0_browser,
    validate_phase0_browser_settings,
)


def _settings(**overrides) -> Settings:
    values = {
        "phase0_browser_enabled": True,
        "phase0_mongodb_uri": "mongodb://phase0.invalid",
        "phase0_mongodb_database": "laclaugpt",
        "phase0_project_id": "ai26",
        "phase0_browser_limit": 25,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _adapted() -> dict:
    return {
        "source_url": "https://example.test/phase0",
        "source_timestamp": "2026-09-20T10:00:00Z",
        "source_author": "Example Lab",
        "source_language": "en",
        "content_title": "Phase 0 item",
        "analysis_status": "analyzed",
        "summary": "A descriptive summary.",
    }


def test_feature_flag_is_off_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.phase0_browser_enabled is False
    validate_phase0_browser_settings(settings)


def test_explicit_configuration_failure_when_enabled_without_phase0_mongo() -> None:
    settings = _settings(phase0_mongodb_uri=None)
    try:
        validate_phase0_browser_settings(settings)
    except Phase0BrowserConfigurationError as exc:
        assert "LACLAUGPT_MONGODB_URI" in str(exc)
    else:
        raise AssertionError("expected explicit Phase 0 browser configuration failure")


def test_limit_is_bounded() -> None:
    settings = _settings(phase0_browser_limit=PHASE0_BROWSER_MAX_LIMIT + 1)
    try:
        validate_phase0_browser_settings(settings)
    except Phase0BrowserConfigurationError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("expected bounded Phase 0 browser limit failure")


def test_collection_name_matches_phase0_contract() -> None:
    assert phase0_collection_name("ai26") == "laclaugpt2_ai26_scraper_collection"


def test_state_covers_ready_empty_and_error() -> None:
    settings = _settings()

    ready = phase0_browser_state(settings, loader=lambda _settings: [_adapted()])
    assert ready.status == "ready"
    assert ready.rows[0]["source_url"] == "https://example.test/phase0"

    empty = phase0_browser_state(settings, loader=lambda _settings: [])
    assert empty.status == "empty"

    error = phase0_browser_state(
        settings,
        loader=lambda _settings: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert error.status == "error"
    assert "offline" in error.message


class _Cursor(list):
    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, limit: int):
        del self[limit:]
        return self


class _Collection:
    def __init__(self, records):
        self.records = records
        self.limit_seen = None

    def find(self, query, projection):
        assert query == {}
        assert projection == {"_id": False}
        return _Cursor(self.records.copy())


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


class _Client:
    def __init__(self, collection):
        self.collection = collection
        self.closed = False

    def __getitem__(self, _name):
        return _Database(self.collection)

    def close(self):
        self.closed = True


def test_loader_is_bounded_and_uses_compatibility_adapter_without_import_time_mongo() -> None:
    raw = [
        {
            "_id": "private-id",
            "source_url": f"https://example.test/{index}",
            "phase0": {"preprocess": {"status": "ok"}},
        }
        for index in range(5)
    ]
    client = _Client(_Collection(raw))
    settings = _settings(phase0_browser_limit=2)

    records = load_phase0_browser_records(
        settings,
        client_factory=lambda *_args, **_kwargs: client,
    )

    assert len(records) == 2
    assert records[0]["source_url"] == "https://example.test/0"
    assert records[0]["phase0_compatibility"]["source_identity"] == "source_url"
    assert client.closed is True


class _Ui:
    def __init__(self):
        self.events = []

    def markdown(self, value):
        self.events.append(("markdown", value))

    def caption(self, value):
        self.events.append(("caption", value))

    def spinner(self, value):
        self.events.append(("spinner", value))
        return nullcontext()

    def error(self, value):
        self.events.append(("error", value))

    def info(self, value):
        self.events.append(("info", value))

    def dataframe(self, value, **kwargs):
        self.events.append(("dataframe", value, kwargs))


def test_renderer_has_explicit_config_failure_state(monkeypatch) -> None:
    settings = _settings(phase0_mongodb_uri=None)
    ui = _Ui()

    render_phase0_browser(ui, settings)

    assert any(kind == "spinner" for kind, *_ in ui.events)
    assert any(kind == "error" and "LACLAUGPT_MONGODB_URI" in value for kind, value in ui.events)


def test_renderer_shows_list_when_loader_state_is_ready(monkeypatch) -> None:
    settings = _settings()
    ui = _Ui()

    monkeypatch.setattr(
        "laclaugpt_visualization.phase0_browser.phase0_browser_state",
        lambda _settings: phase0_browser_state(_settings, loader=lambda __settings: [_adapted()]),
    )
    render_phase0_browser(ui, settings)

    assert any(kind == "dataframe" for kind, *_ in ui.events)
