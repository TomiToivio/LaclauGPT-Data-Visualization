from laclaugpt_visualization.profiles import laptop, linux_service
def test_profiles_keep_configured_analysis_root():
 p=laptop('/synthetic/analysis'); p.validate(); assert str(p.analysis_data_root)=='/synthetic/analysis'
 s=linux_service(storage='distributed'); s.validate(); assert s.execution=='web-service' and s.cache=='redis'
