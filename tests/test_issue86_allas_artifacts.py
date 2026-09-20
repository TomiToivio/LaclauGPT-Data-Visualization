from __future__ import annotations

import sys
from types import SimpleNamespace

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.storage import (
    ArtifactUnavailable,
    artifact_references,
    download_s3_object,
    resolve_artifact_reference,
    safe_artifact_reference,
)


def _s3_settings(**overrides):
    values = {
        "_env_file": None,
        "project_id": "ai26",
        "object_backend": "s3",
        "s3_endpoint_url": "https://object.example.invalid",
        "s3_bucket": "research-placeholder",
    }
    values.update(overrides)
    return Settings(**values)


def test_text_only_records_need_no_object_storage():
    settings = Settings(_env_file=None)
    row = {"source_url": "https://example.invalid/post/1", "source_text": "text only"}

    assert artifact_references(row) == []
    assert settings.object_backend == "local"


def test_artifact_reference_is_project_scoped_and_source_identity_is_untouched():
    settings = _s3_settings()
    row = {
        "source_url": "https://example.invalid/post/1",
        "media_references": [{"object_ref": "media/video.mp4", "content_type": "video/mp4"}],
    }

    references = artifact_references(row)
    assert len(references) == 1
    resolved = resolve_artifact_reference(settings, references[0])

    assert resolved.downloadable is True
    assert resolved.key == "projects/ai26/media/video.mp4"
    assert resolved.filename == "video.mp4"
    assert row["source_url"] == "https://example.invalid/post/1"


def test_cross_project_and_cross_bucket_references_are_rejected():
    settings = _s3_settings()

    other_project = resolve_artifact_reference(
        settings, "s3://research-placeholder/projects/ep24/media/video.mp4"
    )
    other_bucket = resolve_artifact_reference(
        settings, "s3://another-bucket/projects/ai26/media/video.mp4"
    )

    assert other_project.downloadable is False
    assert "different project" in other_project.reason
    assert other_bucket.downloadable is False
    assert "different bucket" in other_bucket.reason


def test_safe_reference_display_removes_credentials_query_and_fragment():
    reference = "https://user:secret@example.invalid/file.mp4?token=super-secret#fragment"

    displayed = safe_artifact_reference(reference)

    assert displayed == "https://example.invalid/file.mp4"
    assert "secret" not in displayed
    assert "token" not in displayed


def test_non_s3_reference_is_displayable_but_not_downloadable():
    settings = _s3_settings()
    resolved = resolve_artifact_reference(settings, "https://cdn.example.invalid/file.mp4?token=x")

    assert resolved.display_reference == "https://cdn.example.invalid/file.mp4"
    assert resolved.downloadable is False
    assert resolved.key is None


def test_mocked_s3_download_uses_project_key_and_ambient_credentials(monkeypatch, tmp_path):
    calls = {}

    class FakeClient:
        def download_file(self, bucket, key, destination):
            calls["download"] = (bucket, key, destination)
            with open(destination, "wb") as handle:
                handle.write(b"fixture")

    def client(service, **kwargs):
        calls["client"] = (service, kwargs)
        return FakeClient()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=client))
    settings = _s3_settings()
    destination = tmp_path / "video.mp4"

    result = download_s3_object(settings, "media/video.mp4", destination)

    assert result == destination
    assert destination.read_bytes() == b"fixture"
    assert calls["download"][:2] == ("research-placeholder", "projects/ai26/media/video.mp4")
    assert calls["client"][0] == "s3"
    assert "aws_access_key_id" not in calls["client"][1]
    assert "aws_secret_access_key" not in calls["client"][1]


def test_download_rejects_project_escape_before_network_transfer(monkeypatch, tmp_path):
    client = SimpleNamespace(download_file=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: client))
    settings = _s3_settings()

    try:
        download_s3_object(settings, "projects/ep24/media/video.mp4", tmp_path / "video.mp4")
    except ValueError as exc:
        assert "unsafe S3/Allas artifact reference" in str(exc)
    else:
        raise AssertionError("cross-project reference should have been rejected")


def test_missing_object_is_reported_without_backend_details(monkeypatch, tmp_path):
    class FakeClient:
        def download_file(self, *args):
            raise RuntimeError("NoSuchKey: private-bucket/projects/ai26/secret.mp4")

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda *args, **kwargs: FakeClient()),
    )
    settings = _s3_settings()

    try:
        download_s3_object(settings, "media/missing.mp4", tmp_path / "missing.mp4")
    except ArtifactUnavailable as exc:
        assert str(exc) == "configured S3/Allas artifact is unavailable"
        assert "private-bucket" not in str(exc)
    else:
        raise AssertionError("missing object should be reported as unavailable")


def test_missing_credentials_are_reported_without_secret_details(monkeypatch, tmp_path):
    def client(*args, **kwargs):
        raise RuntimeError("NoCredentialsError: access-key=do-not-show")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=client))
    settings = _s3_settings()

    try:
        download_s3_object(settings, "media/video.mp4", tmp_path / "video.mp4")
    except ArtifactUnavailable as exc:
        assert str(exc) == "configured S3/Allas artifact is unavailable"
        assert "access-key" not in str(exc)
    else:
        raise AssertionError("missing credentials should be reported as unavailable")
