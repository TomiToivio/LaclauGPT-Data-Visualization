"""Issue #162: the AI26 preflight must be satisfiable by the shipped artifacts.

`deploy/preflight-laskin-ai26.sh` requires `LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`,
while the application default is deliberately `phase0` (compatibility). The variable was
required and documented but provisioned in **no** deployment artifact, so the documented
canonical deployment path could not pass its own `ExecStartPre`:

    ERROR: browser data contract must be canonical

These tests pin the agreement between the preflight's requirement and the artifacts that
configure the service, so the two cannot drift apart again. Nothing here reads private
configuration: only the public preflight, the public service example and the public
`.env.example` are inspected.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "deploy" / "preflight-laskin-ai26.sh"
SERVICE_EXAMPLE = ROOT / "deploy" / "laclaugpt-visualization-laskin-ai26.service.example"
ENV_EXAMPLE = ROOT / ".env.example"
DASHBOARD_DOC = ROOT / "docs" / "AI26_LASKIN_DASHBOARD.md"

CONTRACT_VAR = "LACLAUGPT_VIS_BROWSER_DATA_CONTRACT"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# the preflight's requirement
# --------------------------------------------------------------------------

def test_preflight_requires_the_canonical_contract() -> None:
    """Guard the premise: if this requirement is relaxed, revisit this test file."""
    text = _text(PREFLIGHT)
    assert CONTRACT_VAR in text
    assert re.search(
        rf'\$\{{{CONTRACT_VAR}:-[^}}]*\}}\s*"?"?\)?\s*==\s*"canonical"', text
    ) or f'{CONTRACT_VAR}:-' in text, "preflight must compare the contract to canonical"


def test_preflight_documents_the_variable_in_its_own_error() -> None:
    text = _text(PREFLIGHT)
    assert "browser data contract must be canonical" in text


# --------------------------------------------------------------------------
# the shipped artifacts must be able to satisfy it
# --------------------------------------------------------------------------

def test_service_example_provisions_the_canonical_contract() -> None:
    """A service started from the shipped template must not silently select Phase 0.

    The template already sets two other `Environment=` values, so provisioning the
    contract here is consistent with how the unit is configured.
    """
    text = _text(SERVICE_EXAMPLE)
    assert f"Environment={CONTRACT_VAR}=canonical" in text, (
        "the service example must select the canonical contract explicitly, because the "
        "application default is phase0"
    )


def test_env_example_names_the_variable() -> None:
    """The public example must name it so an operator can find it."""
    text = _text(ENV_EXAMPLE)
    assert CONTRACT_VAR in text


def test_env_example_keeps_the_compatibility_default() -> None:
    """The public example documents the value, and must not imply canonical is default."""
    text = _text(ENV_EXAMPLE)
    match = re.search(rf"^{CONTRACT_VAR}=(.+)$", text, flags=re.MULTILINE)
    assert match, f"{CONTRACT_VAR} must be set in .env.example"
    assert match.group(1).strip() == "phase0", (
        "the public example must keep the deliberate Phase 0 compatibility default; "
        "Phase 1 deployments opt in"
    )


# --------------------------------------------------------------------------
# the preflight and the artifacts must agree
# --------------------------------------------------------------------------

def test_preflight_requirement_is_satisfiable_from_shipped_artifacts() -> None:
    """The agreement itself: the value the preflight demands is the value the
    service template ships."""
    preflight = _text(PREFLIGHT)
    service = _text(SERVICE_EXAMPLE)

    required = re.search(rf'\$\{{{CONTRACT_VAR}:-[^}}]*\}}[^\n]*"([a-z0-9]+)"', preflight)
    assert required, "could not read the required value from the preflight"
    demanded = required.group(1)

    shipped = re.search(rf"^Environment={CONTRACT_VAR}=(.+)$", service, flags=re.MULTILINE)
    assert shipped, "the service example must provision the contract"
    assert shipped.group(1).strip() == demanded, (
        f"preflight requires {demanded!r} but the service example ships "
        f"{shipped.group(1).strip()!r}"
    )


def test_documented_runbook_states_the_contract_for_ai26() -> None:
    """The runbook's profile block must keep the canonical value for AI26."""
    text = _text(DASHBOARD_DOC)
    assert re.search(rf"^{CONTRACT_VAR}=canonical$", text, flags=re.MULTILINE), (
        "the AI26 runbook profile must specify the canonical contract"
    )


def test_no_shipped_artifact_hardcodes_private_values_for_the_contract() -> None:
    """Guard against the fix being done by embedding a private path/host."""
    for path in (SERVICE_EXAMPLE, ENV_EXAMPLE):
        text = _text(path)
        assert "/mnt/workspace" not in text
        assert not re.search(
            r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.", text
        ), f"{path.name} must not contain private network addresses"
