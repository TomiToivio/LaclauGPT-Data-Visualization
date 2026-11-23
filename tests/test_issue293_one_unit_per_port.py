"""One enabled unit owns :8501, and the drift report can tell which one (#293).

The port was healthy, the checkout was at ``origin/main``, the branch was ``main`` and the commit
matched — every existing check passed — while the service answering on :8501 belonged to an
undocumented unit and the documented unit was dead. Both were ``enabled``, so the next start would
have raced for the port.

The missing question is *which unit owns the listening process*. These tests pin it:

* the deployment spec may name the expected unit (``name=port:path#unit``);
* the owner is read from ``/proc/<pid>/cgroup``, in both cgroup layouts;
* a listener owned by another unit is drift, and so is one that no unit owns — the report must not
  call a deployment fine when it could not establish who serves it;
* a spec without a unit keeps the old behaviour exactly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "served-drift-report.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("served_drift_report_293", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drift = _load()

DOCUMENTED = "laclaugpt-visualization-ai26.service"
IMPOSTOR = "laclaugpt-ai26-dashboard.service"


def evaluate(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "branch": "main",
        "head": "8037597abc",
        "upstream": "8037597abc",
        "ahead": 0,
        "behind": 0,
        "listener_cwd": "/srv/example/repo",
        "serving": True,
        "served_unit": DOCUMENTED,
    }
    base.update(overrides)
    deployment = drift.Deployment("ai26", 8501, Path("/srv/example/repo"), unit=DOCUMENTED)
    return drift.evaluate(deployment, **base)


# ------------------------------------------------------------------ the spec


def test_a_deployment_may_name_the_unit_that_must_own_the_port():
    deployment = drift.parse_deployment(f"ai26=8501:/srv/example/repo#{DOCUMENTED}")
    assert deployment.unit == DOCUMENTED
    assert (deployment.port, deployment.path) == (8501, Path("/srv/example/repo"))


def test_the_unit_composes_with_the_detached_mode():
    deployment = drift.parse_deployment(f"live=8503:/srv/repo@detached#{DOCUMENTED}")
    assert (deployment.mode, deployment.unit) == ("detached", DOCUMENTED)


def test_a_spec_without_a_unit_still_parses():
    """Existing deployments keep their behaviour: no unit named, no unit check."""
    deployment = drift.parse_deployment("ai26=8501:/srv/example/repo")
    assert deployment.unit == ""


def test_a_misspelled_spec_is_still_rejected():
    with pytest.raises(ValueError):
        drift.parse_deployment("8501:/srv/example/repo")
    with pytest.raises(ValueError):
        drift.parse_deployment("live=8503:/srv/repo@sideways")


# ------------------------------------------------------------------ the owner


def test_the_unit_is_read_from_a_cgroup_v2_line():
    text = f"0::/user.slice/user-1000.slice/user@1000.service/app.slice/{DOCUMENTED}\n"
    assert drift._unit_from_cgroup(text) == DOCUMENTED


def test_the_unit_is_read_from_a_cgroup_v1_line():
    text = f"4:memory:/user.slice/user-1000.slice/user@1000.service/{DOCUMENTED}\n"
    assert drift._unit_from_cgroup(text) == DOCUMENTED


def test_a_process_outside_a_unit_has_no_owner():
    assert drift._unit_from_cgroup("0::/user.slice/user-1000.slice/session-3.scope\n") == ""
    assert drift._unit_from_cgroup("") == ""


# ------------------------------------------------------------------ the verdict


def test_the_documented_unit_serving_the_port_is_not_drift():
    assert evaluate().ok


def test_the_undocumented_unit_serving_the_port_is_drift():
    """The exact #293 state: right checkout, right commit, wrong unit."""
    state = evaluate(served_unit=IMPOSTOR)
    assert not state.ok
    assert IMPOSTOR in state.problems[0] and DOCUMENTED in state.problems[0]


def test_a_listener_that_no_unit_owns_is_reported_not_passed():
    """`streamlit run` by hand is exactly how the undocumented service started."""
    state = evaluate(served_unit="")
    assert not state.ok
    assert "<no unit>" in state.problems[0]


def test_a_deployment_that_names_no_unit_keeps_its_old_verdict():
    deployment = drift.Deployment("ai26", 8501, Path("/srv/example/repo"))
    state = drift.evaluate(
        deployment,
        branch="main",
        head="8037597abc",
        upstream="8037597abc",
        ahead=0,
        behind=0,
        listener_cwd="/srv/example/repo",
        serving=True,
        served_unit=IMPOSTOR,
    )
    assert state.ok, "a spec that names no unit must not start guessing which unit is right"


# ------------------------------------------------------------------ the installer cannot be silent


def test_the_service_example_configures_the_variable_the_script_reads():
    """A template without it installs a oneshot that inspects nothing and still shows `success`.

    That is how the hourly report ran 184 times without observing anything: the unit set a
    differently spelled variable, the script exited 2, and SuccessExitStatus made 2 a success.
    """
    example = Path(__file__).resolve().parents[1] / "deploy" / "laskin-served-drift.service.example"
    text = example.read_text(encoding="utf-8")
    assert f"Environment={drift.DEPLOYMENTS_ENV}=" in text
    assert "#laclaugpt-visualization-ai26.service" in text


def test_the_runbook_names_the_variable_the_script_reads():
    runbook = Path(__file__).resolve().parents[1] / "docs" / "AI26_LASKIN_DASHBOARD.md"
    assert drift.DEPLOYMENTS_ENV in runbook.read_text(encoding="utf-8")
