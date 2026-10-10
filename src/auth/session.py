"""Who is signed in to this Streamlit session.

Two ways in:
- Email and password: the account id is kept in `st.session_state` for the browser session.
- Google / Microsoft: Streamlit's built-in OpenID Connect (`st.login`), configured in `.streamlit/secrets.toml`
  (see `.streamlit/secrets.toml.example`). The identity cookie survives page reloads.
"""
from __future__ import annotations

import logging

import streamlit as st

from src.auth.accounts import sign_in_external
from src.models.user import User

logger = logging.getLogger(__name__)
SESSION_KEY = "user_id"
SSO_PROVIDERS = {"google": "Google", "microsoft": "Microsoft"}


def configured_providers() -> set[str]:
    """Single-sign-on providers with complete settings in secrets.toml (empty when none are configured)."""
    try:
        auth = st.secrets.get("auth")
    except Exception:  # no secrets.toml at all
        return set()
    if not auth or not auth.get("redirect_uri") or not auth.get("cookie_secret"):
        return set()
    return {name for name in SSO_PROVIDERS
            if hasattr(auth.get(name), "get") and auth[name].get("client_id") and auth[name].get("client_secret")}


def _sso_identity() -> tuple[str, str, str] | None:
    """(email, name, provider) for a user signed in through st.login, else None."""
    user = getattr(st, "user", None)
    if user is None or not getattr(user, "is_logged_in", False):
        return None
    claims = user.to_dict() if hasattr(user, "to_dict") else dict(user)
    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        return None
    issuer = str(claims.get("iss", ""))
    provider = "microsoft" if "microsoft" in issuer else "google" if "google" in issuer else "oidc"
    return email, claims.get("name") or "", provider


def current_user(repo) -> User | None:
    user_id = st.session_state.get(SESSION_KEY)
    if user_id:
        user = repo.get_user(user_id)
        if user:
            return user
        st.session_state.pop(SESSION_KEY, None)
    identity = _sso_identity()
    if identity:
        try:
            user = sign_in_external(repo, *identity)
        except ValueError:
            logger.warning("Single sign-on returned an unusable email address")
            return None
        st.session_state[SESSION_KEY] = user.id
        return user
    return None


def start_session(user: User) -> None:
    st.session_state.clear()
    st.session_state[SESSION_KEY] = user.id


def sign_out() -> None:
    sso = _sso_identity() is not None
    st.session_state.clear()
    if sso:
        st.logout()  # clears the identity cookie and starts a fresh session
    else:
        st.rerun()
