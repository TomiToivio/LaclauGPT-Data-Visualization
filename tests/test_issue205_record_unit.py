"""Regression tests for issue #205: identity is explicit, and counts are auditable."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ep24" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_video_vs_ingest():
    mod = load("export_visualization_data.py")
    first = {"country": "finland", "dataset": "ep24", "source_type": "tiktok",
             "video_id": "00042", "allas_filename": "media/42.mp4",
             "_storage_id": "run-1", "laclau_status": ""}
    second = {**first, "_storage_id": "run-2", "laclau_status": "completed"}
    videos, vqa = mod.normalise([first, second], "finland", "video")
    runs, rqa = mod.normalise([first, second], "finland", "ingest")
    assert len(videos) == 1
    assert videos[0]["_storage_id"] == "run-2"
    assert len(runs) == 2
    assert vqa["records"] == 1 and vqa["distinct_media"] == 1
    assert rqa["records"] == 2 and rqa["distinct_media"] == 1
    assert vqa["duplicate_rows_collapsed"] == 1
    assert mod.row_identity(first, "video") == mod.row_identity(second, "video")
    assert mod.row_identity(first, "ingest") != mod.row_identity(second, "ingest")


def test_canonical_media_identity_separates_segments():
    mod = load("export_visualization_data.py")
    base = {"country": "finland", "source_type": "tiktok", "video_id": "same"}
    assert mod.row_identity({**base, "allas_filename": "a.mp4"}) != mod.row_identity(
        {**base, "allas_filename": "b.mp4"})
    assert mod.row_identity({**base, "source_recording": "a"}) != mod.row_identity(
        {**base, "source_recording": "b"})
    assert not mod.row_identity({**base, "_storage_id": "only-ingest"}, "video")
    assert not mod.row_identity(base, "ingest")


def test_streaming_video_vs_ingest_identity():
    mod = load("export_streaming.py")
    first = {"country": "finland", "source_type": "tiktok", "video_id": "00042",
             "allas_filename": "media/42.mp4", "_storage_id": "run-1"}
    second = {**first, "_storage_id": "run-2"}
    assert mod.identity_key("finland", first) == mod.identity_key("finland", second)
    assert mod.identity_key("finland", first, record_unit="ingest") != mod.identity_key(
        "finland", second, record_unit="ingest")
    assert not mod.identity_key("finland", {"_storage_id": "only"}, record_unit="video")
