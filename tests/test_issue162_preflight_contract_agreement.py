"""Issue #162/#172: shipped AI26 Phase 2 artifacts must agree on the canonical contract.

Issue #162 originally preserved a Phase 0 compatibility default in `.env.example` while
requiring AI26 deployments to opt into `canonical`. That governance decision is superseded
by the repository's AI26 Phase 2-only contract: `canonical` is now the application and
public-example default, while `phase0` remains an explicit historical compatibility mode.

These tests pin agreement between the preflight and the shipped public artifacts so the
Phase 2 default cannot drift back toward the historical contract accidentally. Nothing here
reads private configuration.
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
    """The service template must pin the same canonical AI26 Phase 2 contract."""
    text = _text(SERVICE_EXAMPLE)
    assert f"Environment={CONTRACT_VAR}=canonical" in text, (
        "the service example must explicitly pin the canonical AI26 Phase 2 contract"
    )


def test_env_example_names_the_variable() -> None:
    """The public example must name it so an operator can find it."""
    text = _text(ENV_EXAMPLE)
    assert CONTRACT_VAR in text


def test_env_example_uses_the_phase2_canonical_default() -> None:
    """The public example must reflect the repository's AI26 Phase 2-only default."""
    text = _text(ENV_EXAMPLE)
    match = re.search(rf"^{CONTRACT_VAR}=(.+)$", text, flags=re.MULTILINE)
    assert match, f"{CONTRACT_VAR} must be set in .env.example"
    assert match.group(1).strip() == "canonical", (
        "AI26 Phase 2 ships the canonical browser/data contract by default; "
        "phase0 is historical compatibility only"
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
