from laclaugpt_visualization.profiles import laptop, linux_service


def test_profiles_keep_configured_analysis_root():
    profile = laptop("/synthetic/analysis")
    profile.validate()
    assert profile.analysis_data_root.name == "analysis"

    server = linux_service(storage="distributed")
    server.validate()
    assert server.execution == "web-service"
    assert server.cache == "redis"
