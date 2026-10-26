import json

import pandas as pd
import pytest

from scripts.ep24.export_demo import export


def _input(tmp_path, name, video="v1", **kwargs):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([{"dataset": "ep24", "video_id": video,
                   "allas_filename": video + ".mp4",
                   "country": name, "source_type": "tiktok",
                   "asr_transcript": "evidence",
                   "dna_statements_json": '[{"actor":"A","stance":"support"}]',
                   "model_scratch_prompt": "secret intermediate",
                   **kwargs}]).to_csv(path, index=False)
    return path


def test_three_countries_privacy_and_children(tmp_path):
    inputs = {name: _input(tmp_path, name) for name in ("finland", "poland", "portugal")}
    output = tmp_path / "out"
    manifest = export(inputs, output)
    assert manifest["records"] == 3
    assert manifest["by_country"] == {"finland": 1, "poland": 1, "portugal": 1}
    assert manifest["child_rows"]["dna_statements"] == 3
    data = (output / "combined.csv").read_text()
    assert "model_scratch_prompt" not in data
    assert "asr_transcript" in data
    assert len(list((output / "records.jsonl").open())) == 3
    assert all(json.loads(line)["record_id"] for line in (output / "records.jsonl").open())


def test_invalid_id_excluded(tmp_path):
    inputs = {name: _input(tmp_path, name, video="" if name == "finland" else "v1")
              for name in ("finland", "poland", "portugal")}
    manifest = export(inputs, tmp_path / "out")
    assert manifest["invalid_id_rows_excluded"] == 1
    assert manifest["records"] == 2


def test_country_mismatch_fails(tmp_path):
    inputs = {name: _input(tmp_path, name) for name in ("finland", "poland", "portugal")}
    inputs["finland"] = _input(tmp_path, "finland", country="poland")
    with pytest.raises(ValueError, match="country mismatch"):
        export(inputs, tmp_path / "out")
