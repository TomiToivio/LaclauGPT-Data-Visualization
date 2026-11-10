"""#62: the demo gate is opt-in, constant-time, and never stores the password.

The EP24 export contains author usernames, video identifiers and transcripts. The deployment posture
is network restriction first (Tailscale), shared secret second. This suite covers the second one,
because a gate that can be bypassed by an empty string is worse than no gate: it looks like security.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laclaugpt_visualization.demo_auth import (
    PASSWORD_ENV,
    configured_password,
    password_matches,
)


def test_no_password_configured_means_the_gate_is_off(monkeypatch):
    monkeypatch.delenv(PASSWORD_ENV, raising=False)
    assert configured_password() == ""
    assert password_matches("", "") is True
    assert password_matches("anything", "") is True


def test_a_configured_password_must_be_supplied_exactly(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, "correct horse battery staple")
    assert password_matches("correct horse battery staple", configured_password()) is True
    assert password_matches("correct horse battery stapl", configured_password()) is False
    assert password_matches("", configured_password()) is False


def test_whitespace_around_the_configured_password_is_ignored(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, "  secret  \n")
    assert configured_password() == "secret"
    assert password_matches("secret", configured_password()) is True


def test_the_gate_never_reads_a_password_from_a_file():
    """The password comes from the environment only, so it cannot be committed by accident."""
    source = (Path(__file__).resolve().parents[1]
              / "src/laclaugpt_visualization/demo_auth.py").read_text(encoding="utf-8")
    assert "open(" not in source
    assert "Path(" not in source


def test_the_comparison_is_constant_time():
    source = (Path(__file__).resolve().parents[1]
              / "src/laclaugpt_visualization/demo_auth.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in source


def test_the_app_gates_before_it_reads_any_data():
    """A gate placed after read_records() would still load the corpus into memory."""
    app = (Path(__file__).resolve().parents[1]
           / "src/laclaugpt_visualization/ep24_reprocessed_app.py").read_text(encoding="utf-8")
    gate = app.index("require_demo_password()")
    first_read = app.index("read_records(")
    assert gate < first_read, "the password gate must run before the export is loaded"
