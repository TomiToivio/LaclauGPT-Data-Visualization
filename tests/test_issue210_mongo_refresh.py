"""Synthetic-only contract tests for issue #210."""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ep24/validate_mongo_refresh.py"
spec = importlib.util.spec_from_file_location("validate_mongo_refresh", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_export(root):
    rows = [{"country": country, "record_key": f"{country}/synthetic#{i}",
             "video_id": f"synthetic-{i}", "laclau_status": "pending"}
            for i, country in enumerate(("fi", "pl", "pt"))]
    pd.DataFrame(rows).to_csv(root / "combined.csv", index=False)
    for country in ("fi", "pl", "pt"):
        pd.DataFrame([r for r in rows if r["country"] == country]).to_csv(
            root / f"{country}.csv", index=False)
    manifest = {
        "contract": "ep24-mongo-export/v1", "generated_at": "2026-10-28T10:00:00+00:00",
        "record_unit": "video", "records": 3,
        "record_counts": {c: {"exported": 1, "invalid_ids": 0} for c in ("fi", "pl", "pt")},
        "inputs": {c: {"stage_unavailable": ["9_rdf"]} for c in ("fi", "pl", "pt")},
        "stage_coverage": {c: {"6_discourse": {"records": 0, "available": True}}
                           for c in ("fi", "pl", "pt")},
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_accepts_complete_three_country_export_without_claiming_stage_success(tmp_path):
    make_export(tmp_path)
    report = module.validate(tmp_path)
    assert report["total"] == 3
    assert report["countries"]["fi"]["stage_coverage"]["6_discourse"]["records"] == 0
    assert report["countries"]["pt"]["unavailable_stages"] == ["9_rdf"]


def test_rejects_stale_counts(tmp_path):
    manifest = make_export(tmp_path)
    manifest["record_counts"]["pt"]["exported"] = 100
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="pt: manifest"):
        module.validate(tmp_path)


def test_rejects_duplicate_record_keys(tmp_path):
    make_export(tmp_path)
    df = pd.read_csv(tmp_path / "combined.csv")
    df.loc[1, "record_key"] = df.loc[0, "record_key"]
    df.to_csv(tmp_path / "combined.csv", index=False)
    with pytest.raises(ValueError, match="duplicate record_key"):
        module.validate(tmp_path)


def test_rejects_missing_country(tmp_path):
    manifest = make_export(tmp_path)
    manifest["record_counts"]["pl"]["exported"] = 0
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="pl: manifest|pl: no exported"):
        module.validate(tmp_path)
