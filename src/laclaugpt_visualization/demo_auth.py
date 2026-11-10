"""Optional shared-secret gate for the researcher demo (#62).

The EP24 export contains author usernames, video identifiers and transcripts. The issue's security
gate says that exposure must be a decision, not an accident — so the app can require a password
without the password ever living in the repository.

Behaviour:

* ``LACLAUGPT_VIS_DEMO_PASSWORD`` unset → the gate is disabled and the app behaves exactly as before.
  That is the current posture on the LAN/Tailscale deployment: reachable only inside the private
  network, not from the open internet.
* set → a single password form is shown before any data is read. The comparison is constant-time.

The password is never written to disk here, never logged, and never printed.
"""
from __future__ import annotations

import hmac
import os

PASSWORD_ENV = "LACLAUGPT_VIS_DEMO_PASSWORD"


def configured_password() -> str:
    """The password expected by this deployment, or an empty string when the gate is off."""
    return (os.environ.get(PASSWORD_ENV) or "").strip()


def password_matches(supplied: str, expected: str) -> bool:
    """Constant-time comparison. An empty expectation means the gate is disabled."""
    if not expected:
        return True
    return hmac.compare_digest(supplied or "", expected)


def require_demo_password() -> bool:
    """Render the gate if one is configured. Returns True when the viewer may continue.

    Imported lazily so this module stays importable in tests without Streamlit installed.
    """
    expected = configured_password()
    if not expected:
        return True

    import streamlit as st  # imported here on purpose

    if st.session_state.get("demo_authenticated") is True:
        return True

    st.title("EP24 researcher dashboard")
    st.caption("This export contains author usernames, video identifiers and transcripts.")
    with st.form("demo_gate", clear_on_submit=False):
        supplied = st.text_input("Access password", type="password")
        submitted = st.form_submit_button("Open dashboard")
    if submitted:
        if password_matches(supplied, expected):
            st.session_state["demo_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()
    return False
