from laclaugpt_visualization.acdt_compat import (
    metadata_panel,
    normalize_result,
    result_products,
    semantic_warning,
    theoretical_labels_authorized,
)
from laclaugpt_visualization.products import ProductKind


def test_legacy_result_without_new_fields_renders_gracefully():
    legacy = {"plugin": "old_topic_model", "plugin_version": "0.9", "output": {"rows": [{"topic": 1}]}}
    normalized = normalize_result(legacy)
    assert normalized["schema_version"] == "legacy/not_available"
    assert normalized["interpretation_mode"] == "not_available"
    products = result_products(legacy)
    assert ProductKind.TABLE in products
    assert products[ProductKind.TABLE].payload == [{"topic": 1}]


def test_peak_result_maps_to_timeline_and_keeps_method_metadata():
    result = {
        "schema_version": "acdt-result/1.0",
        "method_id": "peak_analysis",
        "method_version": "1.0",
        "interpretation_mode": "exploratory_instrumentalist",
        "study_id": "ai26",
        "input_record_ids": ["x:1"],
        "provenance": {"producer": "analysis"},
        "validation": {"status": "not_applicable", "human_review_status": "provisional"},
        "output": {"series": [{"date": "2026-09-17", "count": 4}], "peaks": []},
    }
    products = result_products(result)
    timeline = products[ProductKind.TIMELINE]
    assert timeline.metadata["method_id"] == "peak_analysis"
    assert "frequency is not hegemony" in timeline.metadata["semantic_warning"].lower()


def test_hashtag_network_does_not_authorize_theoretical_labels():
    result = {
        "schema_version": "acdt-result/1.0",
        "method_id": "hashtag_cooccurrence",
        "method_version": "1.0",
        "interpretation_mode": "exploratory_instrumentalist",
        "provenance": {"producer": "analysis"},
        "validation": {"status": "not_applicable", "human_review_status": "reviewed"},
        "output": {"nodes": [], "edges": []},
    }
    assert theoretical_labels_authorized(result) is False
    assert "not automatically articulation" in semantic_warning(result).lower()


def test_only_reviewed_theoretical_output_can_present_validated_theoretical_labels():
    result = {
        "method_id": "laclau_discourse_analysis",
        "interpretation_mode": "theoretical_interpretive",
        "validation": {"status": "validated", "human_review_status": "reviewed"},
        "provenance": {"producer": "analysis"},
        "output": {"label": "explicit source-side analysis"},
    }
    assert theoretical_labels_authorized(result) is True
    assert metadata_panel(result)["validation"]["human_review_status"] == "reviewed"
