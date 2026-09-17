from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.distributed import ProjectNamespace
from laclaugpt_visualization.storage import redis_cache_key, redis_control_key


def test_visualization_namespace_derivation() -> None:
    ns = ProjectNamespace("ai26")
    assert ns.settings_key("visualization") == "laclaugpt:ai26:settings:visualization:current"
    assert ns.mongo_collection("annotations") == "ai26__annotations"
    assert ns.s3_key("exports", "latest.csv") == "projects/ai26/exports/latest.csv"


def test_settings_default_mongodb_collection_is_project_scoped() -> None:
    settings = Settings(_env_file=None, project_id="ep24")
    assert settings.resolved_mongodb_collection == "ep24__annotations"


def test_periodic_summary_collection_kind_matches_analysis_namespace() -> None:
    ns = ProjectNamespace("ai26")
    assert ns.mongo_collection("periodic_summaries") == "ai26__periodic_summaries"


def test_redis_helpers_stay_inside_project_namespace() -> None:
    settings = Settings(_env_file=None, project_id="hungary26")
    assert redis_cache_key(settings, "monitor") == "laclaugpt:hungary26:cache:monitor"
    assert redis_control_key(settings, "manifest") == "laclaugpt:hungary26:manifest:current"


def test_named_projects_do_not_collide() -> None:
    names = ("ai26", "ep24", "brazil26", "hungary26")
    namespaces = [ProjectNamespace(name) for name in names]
    assert len({item.mongo_collection("annotations") for item in namespaces}) == len(names)
    assert len({item.s3_key("exports") for item in namespaces}) == len(names)
