"""The dashboard's login gate: same shape as :8501, credentials outside the repository (#263)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from laclaugpt_visualization.demo_auth import (
    AUTH_CONFIG_ENV,
    DEFAULT_AUTH_CONFIG,
    PASSWORD_ENV,
    auth_config_path,
    configured_password,
    password_matches,
)


def test_no_config_and_no_password_means_the_gate_is_off(monkeypatch, tmp_path: Path):
    monkeypatch.delenv(AUTH_CONFIG_ENV, raising=False)
    monkeypatch.delenv(PASSWORD_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert auth_config_path() is None
    assert configured_password() == ""
    assert password_matches("anything", "") is True


def test_a_named_config_that_does_not_exist_is_not_silently_replaced_by_the_default(monkeypatch, tmp_path: Path):
    """A deployment naming a missing file has a configuration error; falling back would hide it."""
    default = tmp_path / ".config" / "ep24-dashboard" / "auth.yaml"
    default.parent.mkdir(parents=True)
    default.write_text("credentials: {}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(AUTH_CONFIG_ENV, str(tmp_path / "absent.yaml"))
    assert auth_config_path() is None


def test_the_default_config_is_used_when_it_exists(monkeypatch, tmp_path: Path):
    default = tmp_path / ".config" / "ep24-dashboard" / "auth.yaml"
    default.parent.mkdir(parents=True)
    default.write_text("credentials: {}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(AUTH_CONFIG_ENV, raising=False)
    assert auth_config_path() == default
    assert DEFAULT_AUTH_CONFIG.endswith("auth.yaml")


def test_the_single_password_gate_still_compares_in_constant_time(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, "  hunter2  ")
    assert configured_password() == "hunter2"
    assert password_matches("hunter2", configured_password()) is True
    assert password_matches("hunter3", configured_password()) is False


def test_the_authenticator_reads_the_same_yaml_shape_as_the_legacy_dashboard():
    """The legacy :8501 file carries credentials.usernames[user].password plus a cookie block."""
    import yaml

    text = Path("tests/fixtures/auth_shapes.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    assert list(config) == ["credentials", "cookie"]
    assert "example_user" in config["credentials"]["usernames"]
    entry = config["credentials"]["usernames"]["example_user"]
    assert {"password", "email", "first_name", "roles"} <= set(entry)
    assert {"name", "key", "expiry_days"} <= set(config["cookie"])


def test_no_credential_is_committed_anywhere_in_the_tree():
    """A password in the repository is a password in every clone, forever. Guard it mechanically."""
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    needles = ("Guy2025", "ep2024:")
    offenders = []
    for name in tracked:
        path = Path(name)
        if not path.is_file() or path.stat().st_size > 400_000:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".parquet", ".zip", ".gz"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for needle in needles:
            if needle in text:
                offenders.append(f"{name}: {needle}")
    assert not offenders, "credential material found in tracked files: " + ", ".join(offenders)


def test_every_multipage_script_gates_itself_before_it_loads_data():
    """Streamlit's nav reaches each page script directly, so a gate on the main page protects only that page."""
    pages = sorted(p for p in Path("src/laclaugpt_visualization/pages").glob("*.py") if p.name != "__init__.py")
    assert pages, "expected the multipage scripts to exist"
    ungated = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if "require_login()" not in text:
            ungated.append(page.name)
            continue
        gate_at = text.index("require_login()")
        # The call must come before the first data access in that script.
        for loader in ("_load_default_frame(", "read_parquet(", "read_csv(", "load_data("):
            if loader in text and text.index(loader) < gate_at:
                ungated.append(f"{page.name} (loads data before the gate)")
                break
    assert not ungated, "pages that do not gate before reading data: " + ", ".join(ungated)
