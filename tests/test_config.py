from pathlib import Path

from laclaugpt_visualization.config import Settings


def test_runtime_defaults_stay_under_data() -> None:
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("data")
    assert settings.output_dir == Path("data/exports")
    assert settings.sqlite_path == Path("data/database/visualization.sqlite3")
    assert settings.analysis_data_dir is None


def test_same_machine_analysis_path_is_configurable() -> None:
    settings = Settings(
        _env_file=None,
        analysis_data_dir=Path("../LaclauGPT-Data-Analysis/data"),
    )
    assert settings.analysis_data_dir == Path("../LaclauGPT-Data-Analysis/data")
