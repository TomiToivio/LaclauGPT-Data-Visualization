"""Adapters from shared AC/DT analysis envelopes to backend-neutral data products.

This module is deliberately conservative: it renders what an analysis result says but
never upgrades visual proximity, clusters, sentiment, topic membership or co-occurrence
into Laclaudian theoretical claims.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .products import DataProduct, EvidenceRef, ProductKind

ACDT_RESULT_SCHEMA = "acdt-result/1.0"


def normalize_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize current and legacy result envelopes without inventing missing metadata."""
    result = deepcopy(dict(value))
    result.setdefault("schema_version", "legacy/not_available")
    result.setdefault("method_id", result.get("plugin") or "not_available")
    result.setdefault("method_version", result.get("plugin_version") or "not_available")
    result.setdefault("interpretation_mode", "not_available")
    result.setdefault("study_id", None)
    result.setdefault("corpus_id", None)
    result.setdefault("input_record_ids", [])
    result.setdefault("parameters", {})
    result.setdefault("provenance", {"producer": "not_available"})
    result.setdefault(
        "validation",
        {
            "status": "not_available",
            "human_review_status": "not_available",
            "method": None,
            "notes": None,
        },
    )
    result.setdefault("evidence_refs", [])
    if "output" not in result:
        result["output"] = {}
    return result


def metadata_panel(result: Mapping[str, Any]) -> dict[str, Any]:
    """Small metadata payload suitable for an always-visible provenance panel."""
    item = normalize_result(result)
    return {
        "schema_version": item["schema_version"],
        "method_id": item["method_id"],
        "method_version": item["method_version"],
        "interpretation_mode": item["interpretation_mode"],
        "study_id": item["study_id"],
        "corpus_id": item["corpus_id"],
        "provenance": item["provenance"],
        "validation": item["validation"],
    }


def theoretical_labels_authorized(result: Mapping[str, Any]) -> bool:
    """Whether a result may display its own explicit theoretical labels as validated.

    Even when true, this function does not infer a label. It only permits rendering an
    already present theoretical interpretation from a reviewed result.
    """
    item = normalize_result(result)
    review = str(item.get("validation", {}).get("human_review_status", "")).lower()
    return item.get("interpretation_mode") == "theoretical_interpretive" and review in {
        "reviewed",
        "accepted",
        "canonical",
    }


def semantic_warning(result: Mapping[str, Any]) -> str:
    item = normalize_result(result)
    method = item["method_id"]
    if method in {"hashtag_cooccurrence", "social_network_analysis", "discourse_network_analysis"}:
        return "Network structure/co-occurrence is evidence, not automatically articulation, equivalence, ideology or hegemony."
    if method in {"sentiment_analysis", "emotion_analysis", "emotion_intensity"}:
        return "Sentiment/emotion is an auxiliary measurement, not Laclaudian affective investment."
    if method in {"topic_model_lda", "topic_model_generic"}:
        return "A topic is a computational pattern, not automatically a frame, discourse or ideology."
    if method in {"wordscores", "wordfish"}:
        return "A latent scale is not an ideological label without substantive validation."
    if method == "peak_analysis":
        return "A temporal peak selects high-intensity material for interpretation; frequency is not hegemony."
    return "Computational outputs remain evidence or measurements unless a reviewed theoretical analysis explicitly says otherwise."


def _evidence_refs(item: Mapping[str, Any]) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for raw in item.get("evidence_refs", []) or []:
        if not isinstance(raw, Mapping):
            continue
        record_id = str(raw.get("record_id") or raw.get("source_url") or "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        refs.append(
            EvidenceRef(
                record_id=record_id,
                source_url=raw.get("source_url"),
                artifact_id=raw.get("artifact_id"),
                selector=dict(raw.get("selector") or {}),
            )
        )
    return tuple(refs)


def result_products(value: Mapping[str, Any]) -> dict[ProductKind, DataProduct]:
    """Project an AC/DT envelope into products already understood by the dashboard."""
    item = normalize_result(value)
    method = str(item["method_id"])
    output = item.get("output")
    output = dict(output) if isinstance(output, Mapping) else {"value": output}
    metadata = metadata_panel(item)
    metadata["semantic_warning"] = semantic_warning(item)
    evidence = _evidence_refs(item)
    project = item.get("study_id")
    dataset = item.get("corpus_id")
    version = str(item.get("method_version") or "not_available")

    products: dict[ProductKind, DataProduct] = {}
    if method in {"hashtag_cooccurrence", "social_network_analysis", "discourse_network_analysis"}:
        products[ProductKind.NETWORK] = DataProduct(
            kind=ProductKind.NETWORK,
            payload={"nodes": output.get("nodes", []), "edges": output.get("edges", [])},
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
    elif method == "peak_analysis":
        products[ProductKind.TIMELINE] = DataProduct(
            kind=ProductKind.TIMELINE,
            payload={"series": output.get("series", []), "peaks": output.get("peaks", [])},
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
    elif method == "close_reading_sampler":
        products[ProductKind.RECORDS] = DataProduct(
            kind=ProductKind.RECORDS,
            payload=output.get("samples", output.get("record_ids", [])),
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
    elif method == "multimodal_rhetoric_performative":
        products[ProductKind.RECORDS] = DataProduct(
            kind=ProductKind.RECORDS,
            payload=output,
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
        media = output.get("media") or output.get("frames") or []
        products[ProductKind.MEDIA] = DataProduct(
            kind=ProductKind.MEDIA,
            payload=media,
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
    else:
        rows = output.get("rows")
        if rows is None:
            rows = output.get("topics")
        if rows is None:
            rows = output.get("values")
        if rows is None:
            rows = output
        products[ProductKind.TABLE] = DataProduct(
            kind=ProductKind.TABLE,
            payload=rows,
            project=project,
            dataset=dataset,
            version=version,
            metadata=metadata,
            evidence=evidence,
        )
    return products
