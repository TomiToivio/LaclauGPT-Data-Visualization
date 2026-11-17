"""Username/password gate in the same shape as the legacy `:8501` dashboard (#263).

`:8501` protects itself with `streamlit-authenticator` reading `auth.yaml` (users, bcrypt-or-plain passwords,
cookie name/key/expiry). This module gives `:8502` the same behaviour, with three differences that matter:

* the config file lives **outside the repository**, at ``LACLAUGPT_VIS_AUTH_CONFIG`` or
  ``~/.config/ep24-dashboard/auth.yaml``, and is expected to be mode 0600 — a credential must never be
  committable by accident;
* a missing config file disables the gate rather than leaving a half-configured login; the app says which
  state it is in, so "protected" is never assumed;
* if the single-password gate (``LACLAUGPT_VIS_DEMO_PASSWORD``) is also configured, it keeps working — the two
  gates are alternatives, not layers.

Nothing here reads, logs or returns the password.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

PASSWORD_ENV = "LACLAUGPT_VIS_DEMO_PASSWORD"
AUTH_CONFIG_ENV = "LACLAUGPT_VIS_AUTH_CONFIG"
DEFAULT_AUTH_CONFIG = "~/.config/ep24-dashboard/auth.yaml"


def configured_password() -> str:
    """The password expected by the single-password gate, or an empty string when that gate is off."""
    return (os.environ.get(PASSWORD_ENV) or "").strip()


def password_matches(supplied: str, expected: str) -> bool:
    """Constant-time comparison. An empty expectation means the gate is disabled."""
    if not expected:
        return True
    return hmac.compare_digest(supplied or "", expected)


def auth_config_path() -> Path | None:
    """The authentication config in use, or ``None`` when no file exists.

    An explicit ``LACLAUGPT_VIS_AUTH_CONFIG`` wins even when it points at nothing: a deployment that names a
    missing file has a configuration error, and silently falling back to the default path would hide it.
    """
    explicit = (os.environ.get(AUTH_CONFIG_ENV) or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() else None
    default = Path(DEFAULT_AUTH_CONFIG).expanduser()
    return default if default.is_file() else None


def authenticator_from(config_path: Path) -> Any:
    """A configured ``streamlit_authenticator.Authenticate`` for this deployment's file.

    Imported lazily so the module stays importable (and testable) without Streamlit installed.
    """
    import streamlit_authenticator as stauth
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    credentials = config.get("credentials") or {}
    cookie = config.get("cookie") or {}
    return stauth.Authenticate(
        credentials=credentials,
        cookie_name=cookie.get("name", "ep24_researcher"),
        cookie_key=cookie.get("key") or "",
        cookie_expiry_days=float(cookie.get("expiry_days", 1)),
    )


def render_login_gate(authenticator: Any) -> bool:
    """Show the login form; return True only for an authenticated session.

    Rendered before any export is read, so an unauthenticated visitor never causes the corpus to be loaded.
    """
    import streamlit as st

    if st.session_state.get("authentication_status") is True:
        return True

    try:
        authenticator.login(location="main")
    except TypeError:  # older/newer streamlit-authenticator signatures
        authenticator.login()
    status = st.session_state.get("authentication_status")
    if status is True:
        return True
    if status is False:
        st.error("Username/password is incorrect.")
    else:
        st.warning("Please enter your username and password.")
    st.caption("This export contains author usernames, video identifiers and transcripts.")
    return False


def require_demo_password() -> bool:
    """Render the single-password gate if one is configured. Returns True when the viewer may continue."""
    expected = configured_password()
    if not expected:
        return True

    import streamlit as st

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


def require_login() -> bool:
    """Gate the app: username/password when a config file exists, else the single-password gate.

    Returns True when the viewer may continue; otherwise stops the script after rendering the form, so no view
    below can render against a frame nobody is entitled to see.
    """
    config_path = auth_config_path()
    if config_path is None:
        return require_demo_password()

    import streamlit as st

    if not render_login_gate(authenticator_from(config_path)):
        st.stop()
    email = st.session_state.get("email") or ""
    if email:
        st.sidebar.caption(f"Signed in as {email}.")
    return True
