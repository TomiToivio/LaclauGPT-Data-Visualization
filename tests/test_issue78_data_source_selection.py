from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from laclaugpt_visualization import storage
from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.phase0_browser import phase0_collection_name
from laclaugpt_visualization.query_backends import BackendUnavailable


def test_phase0_is_the_explicit_browser_contract_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.browser_data_contract == "phase0"


def test_phase0_selector_uses_the_phase0_collection_contract() -> None:
    settings = Settings(_env_file=None, project_id="ai26", phase0_project_id="ai26")

    assert phase0_collection_name(settings.resolved_phase0_project_id) == (
        "laclaugpt2_ai26_scraper_collection"
    )


def test_phase0_and_canonical_configuration_namespaces_are_isolated() -> None:
    settings = Settings(
        _env_file=None,
        project_id="canonical-study",
        mongodb_database="canonical-db",
        mongodb_collection="canonical-records",
        phase0_project_id="legacy-study",
        phase0_mongodb_database="legacy-db",
    )

    assert settings.mongodb_database == "canonical-db"
    assert settings.resolved_mongodb_collection == "canonical-records"
    assert settings.phase0_mongodb_database == "legacy-db"
    assert phase0_collection_name(settings.resolved_phase0_project_id) == (
        "laclaugpt2_legacy-study_scraper_collection"
    )


def test_canonical_loader_uses_only_the_canonical_backend(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        browser_data_contract="canonical",
        mongodb_uri="mongodb://canonical.invalid",
    )
    expected = pd.DataFrame([{"source_url": "https://example.test/canonical"}])

    class Product:
        payload = expected

    class Backend:
        def records(self, *, limit=None):
            assert limit == 100
            return Product()

    monkeypatch.setattr(storage.MongoQueryBackend, "from_settings", lambda current: Backend())

    result = storage.load_canonical_mongodb(settings)

    assert result is expected
    assert settings.browser_data_contract == "canonical"


def test_canonical_loader_never_falls_back_to_local_or_phase0(monkeypatch) -> None:
    settings = Settings(_env_file=None, mongodb_uri=None)

    monkeypatch.setattr(
        storage,
        "load_local_frame",
        lambda _settings: (_ for _ in ()).throw(AssertionError("unexpected local fallback")),
    )

    with pytest.raises(BackendUnavailable, match="Canonical Phase 1 browser requires"):
        storage.load_canonical_mongodb(settings)


def test_browser_selector_is_explicit_reversible_and_precedes_rendering() -> None:
    source = Path("src/laclaugpt_visualization/app.py").read_text(encoding="utf-8")

    selector = source.index('"Data source contract"')
    phase0_render = source.index("render_phase0_browser(st, settings)", selector)
    canonical_render = source.index("_render_canonical_browser(settings)", selector)

    assert selector < phase0_render
    assert selector < canonical_render
    assert "Phase 0 compatibility contract" in source
    assert "Canonical Phase 1 contract" in source
    assert '("phase0", "canonical")' in source
