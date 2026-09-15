import json
from pathlib import Path

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.integrations.hermes import (
    export_summary,
    inspect_effective_config,
    request_human_review,
    validate_analysis_input,
    validate_service,
)


def _local_settings(tmp_path: Path, **overrides) -> Settings:
    data_dir = tmp_path / "data"
    values = {
        "_env_file": None,
        "project_id": "ai26",
        "data_dir": data_dir,
        "output_dir": data_dir / "exports",
        "sqlite_path": data_dir / "database" / "visualization.sqlite3",
    }
    values.update(overrides)
    return Settings(**values)


def _sample_jsonl(tmp_path: Path) -> Path:
    path = tmp_path / "sample.jsonl"
    path.write_text(
        json.dumps(
            {
                "source_url": "https://example.invalid/post/1",
                "schema_version": "1.0",
                "source_platform": "synthetic",
                "source_country": "XX",
                "source_language": "en",
                "analysis_status": "complete",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_laptop_profile_is_local_and_requires_no_remote_services(tmp_path: Path) -> None:
    settings = _local_settings(tmp_path)
    settings.validate_remote_requirements()
    profile = settings.deployment_profile
    assert (profile.machine, profile.execution, profile.storage, profile.cache) == (
        "laptop",
        "cli",
        "local",
        "memory",
    )


def test_server_convenience_profile_maps_to_linux_web_service(tmp_path: Path) -> None:
    settings = _local_settings(tmp_path, profile="server")
    profile = settings.deployment_profile
    assert profile.machine == "linux-server"
    assert profile.execution == "web-service"
    assert profile.storage == "local"


def test_distributed_profile_validates_offline_without_connections(tmp_path: Path) -> None:
    settings = _local_settings(
        tmp_path,
        machine="linux-server",
        execution="web-service",
        storage="distributed",
        data_backend="mongodb",
        cache_backend="redis",
        object_backend="s3",
        mongodb_uri="mongodb://localhost:27017",
        redis_url="redis://localhost:6379/0",
        s3_endpoint_url="https://object.example.invalid",
        s3_bucket="research-placeholder",
    )
    settings.validate_remote_requirements()
    summary = inspect_effective_config(settings)
    assert summary["storage"] == "distributed"
    assert "mongodb_uri" not in summary
    assert "redis_url" not in summary


def test_hermes_uses_canonical_loader_and_audits_actions(tmp_path: Path) -> None:
    settings = _local_settings(tmp_path)
    source = _sample_jsonl(tmp_path)
    validation = validate_analysis_input(source, settings)
    assert validation["records"] == 1
    assert validation["missing_source_url"] == 0
    assert validation["valid"] is True

    exported = export_summary(source, settings)
    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert payload["caller"] == "hermes-agent"
    assert payload["execution"] == "agent"
    assert payload["project_id"] == "ai26"

    audit = request_human_review("https://example.invalid/post/1", settings)
    action = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert action["source_url"] == "https://example.invalid/post/1"
    assert action["caller"] == "hermes-agent"


def test_health_is_offline_and_rejects_slurm(tmp_path: Path) -> None:
    settings = _local_settings(tmp_path)
    settings.ensure_local_directories()
    result = validate_service(settings)
    assert result["status"] == "ready"
    assert result["command"][0:3] == ["python", "-m", "streamlit"]
