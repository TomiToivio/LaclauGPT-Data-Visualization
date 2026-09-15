"""Bounded compatibility adapter for legacy EP24-shaped flat records."""
from __future__ import annotations
from typing import Any

def adapt(record: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version":"legacy-ep24-adapter-1","document_id":str(record.get("video_id") or record.get("id") or ""),"source_platform":record.get("platform", ""),"source_timestamp":record.get("date") or record.get("timestamp") or "","summary":record.get("summary") or record.get("analysis_summary") or "","transcript":record.get("transcript") or "","ocr":record.get("ocr") or "","entities":record.get("entities") or [],"topics":record.get("topics") or record.get("themes") or [],"review_status":record.get("review_status") or "pending","provenance":{"adapter":"legacy_ep24"}}
