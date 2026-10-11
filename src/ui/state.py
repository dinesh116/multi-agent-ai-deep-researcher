"""Shared UI state: identity (login / guest), repository, settings, selected run and sidebar.

Identity:
- If Google sign-in is configured ([auth] in Streamlit secrets), signed-in users are identified by their stable
  provider subject id; visitors who are not signed in get a temporary per-session guest id (demo mode only).
- Only APP_ENV=local permits a single local administrator without configured authentication.
Every repository call passes the current user's id, so data is private per user.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from urllib.parse import urlsplit
import uuid
from dataclasses import dataclass

import streamlit as st

from html import escape

from src.config import APP_NAME, Settings, get_settings
from src.database.repository import LOCAL_OWNER, Repository
from src.models.run import RunBundle
from src.search.registry import ProviderSettings

DEFAULTS = {"depth": "standard", "max_iterations": 2, "mode": "live", "use_llm": True, "include_demo_banner": True}


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    name: str
    is_guest: bool
    is_admin: bool
    auth_enabled: bool
    picture: str | None = None

    @property
    def can_use_live(self) -> bool:
        return not self.is_guest


@st.cache_resource
def get_repo() -> Repository:
    require_auth_configuration()
    settings = get_settings()
    repo = Repository(settings.db_path, settings.turso_database_url, settings.turso_auth_token)
    repo.reap_stale_runs(settings.run_stale_after_seconds)  # only runs whose worker stopped heartbeating
    repo.purge_guest_data()
    return repo


logger = logging.getLogger(__name__)


def auth_enabled() -> bool:
    """Validate configuration and optionally log field status, never values or exception text."""
    fields = {}
    error_type = None
    callback_https = callback_path_ok = callback_local = False
    try:
        auth = st.secrets.get("auth", {})
        provider = auth.get("google", {})
        fields = {"auth.redirect_uri": auth.get("redirect_uri"),
                  "auth.cookie_secret": auth.get("cookie_secret"),
                  "auth.google.client_id": provider.get("client_id"),
                  "auth.google.client_secret": provider.get("client_secret"),
                  "auth.google.server_metadata_url": provider.get("server_metadata_url")}
        fields = {name: bool(isinstance(value, str) and value.strip() and "<" not in value)
                  for name, value in fields.items()}
        valid = all(fields.values())
        if fields["auth.redirect_uri"]:
            try:
                callback = urlsplit(auth.get("redirect_uri"))
                callback_https = callback.scheme == "https"
                callback_path_ok = callback.path == "/oauth2callback"
                callback_local = callback.hostname in {"localhost", "127.0.0.1", "::1"}
            except ValueError:
                pass
    except Exception as exc:
        valid = False
        error_type = type(exc).__name__
    diagnostics = os.getenv("AUTH_DIAGNOSTICS", "false").lower() in {"true", "1", "yes"}
    signature = (valid, tuple(fields.items()), error_type, callback_https, callback_path_ok, callback_local)
    if diagnostics and st.session_state.get("_auth_diagnostic_signature") != signature:
        logger.warning("AUTH_CONFIG valid=%s field_status=%s secrets_error_type=%s "
                       "callback_https=%s callback_path_ok=%s callback_local=%s",
                       valid, fields, error_type, callback_https, callback_path_ok, callback_local)
        st.session_state["_auth_diagnostic_signature"] = signature
    return valid


def login_google() -> None:
    """Log login initiation and synchronous failures without exposing OAuth data."""
    logger.warning("AUTH_LOGIN_START provider=google")
    try:
        st.login("google")
    except Exception as exc:
        logger.error("AUTH_LOGIN_FAILED exception_type=%s", type(exc).__name__)
        st.error("Google sign-in could not start. Check authentication configuration and server logs.")


def require_auth_configuration() -> None:
    """Stop deployed apps before opening the shared repository when auth is unavailable."""
    if get_settings().app_env != "local" and not auth_enabled():
        logger.error("AUTH_BLOCKED production authentication configuration is missing, incomplete or unreadable")
        st.error("Authentication is required in production. Configure Google sign-in in Streamlit Secrets. "
                 "For a private local development session only, explicitly set APP_ENV=local.")
        st.stop()


def current_user() -> CurrentUser:
    require_auth_configuration()
    settings = get_settings()
    if not auth_enabled():
        return CurrentUser(LOCAL_OWNER, None, "Local user", is_guest=False, is_admin=True, auth_enabled=False)
    if st.user.get("is_logged_in", False):  # st.user may lack the attribute before auth initialises
        subject = st.user.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            logger.error("AUTH_SESSION_INVALID provider subject is missing or invalid")
            st.error("Your sign-in session has no valid identity. Please sign out and sign in again.")
            st.stop()
        user_id = subject
        email = (st.user.get("email") or "").lower() or None
        if st.session_state.get("_user_recorded") != user_id:  # once per session: profile + login activity
            logger.warning("AUTH_SESSION_ACCEPTED provider=google subject_present=true")
            repo = get_repo()
            repo.upsert_user(user_id, email, st.user.get("name"), st.user.get("picture"), provider="google")
            repo.log_activity(user_id, "login", detail={"email": email})
            st.session_state["_user_recorded"] = user_id
        return CurrentUser(user_id, email, st.user.get("name") or email or "Signed-in user", is_guest=False,
                           is_admin=bool(email and email in settings.admin_emails), auth_enabled=True,
                           picture=st.user.get("picture"))
    guest = st.session_state.setdefault("_guest_id", f"guest:{uuid.uuid4().hex[:12]}")
    return CurrentUser(guest, None, "Guest", is_guest=True, is_admin=False, auth_enabled=True)


def effective_settings() -> Settings:
    """Environment settings plus admin overrides (model names). These are app-wide, set by an admin."""
    settings = get_settings()
    model = get_repo().get_setting("llm_model")
    return dataclasses.replace(settings, openrouter_model=model) if model else settings


def provider_settings() -> ProviderSettings:
    stored = get_repo().get_setting("providers", {})
    return ProviderSettings(**{k: v for k, v in stored.items() if k in ProviderSettings.__dataclass_fields__})


def preference(key: str):
    """Personal preference of the current user, falling back to the app default."""
    user = current_user()
    value = get_repo().get_user_setting(user.id, f"pref_{key}")
    return value if value is not None else DEFAULTS[key]


def selected_run_id() -> str | None:
    run_id = st.session_state.get("selected_run_id")
    if run_id:
        return run_id
    runs = [r for r in get_repo().list_runs(current_user().id, limit=5) if r.status == "completed"]
    return runs[0].id if runs else None


def load_selected_run() -> RunBundle | None:
    """The selected run, only if it belongs to the current user (otherwise nothing is shown)."""
    run_id = selected_run_id()
    if not run_id:
        return None
    user = current_user()
    cache = st.session_state.setdefault("_bundle_cache", {})
    key = (user.id, run_id)
    if key not in cache:
        bundle = get_repo().load_run(run_id, user.id)
        if bundle is None:
            st.session_state.pop("selected_run_id", None)
            return None
        cache.clear()
        cache[key] = bundle
    return cache[key]


def select_run(run_id: str) -> None:
    st.session_state["selected_run_id"] = run_id
    st.session_state.pop("_bundle_cache", None)


def require_run() -> RunBundle:
    bundle = load_selected_run()
    if bundle is None:
        st.info("No research selected yet. Start an investigation in the **Research workspace**, or open one "
                "from the **Research library**.", icon=":material/info:")
        st.page_link("app_pages/1_Research_Workspace.py", label="Go to Research Workspace", icon=":material/arrow_forward:")
        st.stop()
    return bundle


def new_research() -> None:
    """Clear the workspace form and open it."""
    for key in [k for k in st.session_state if k.startswith("q_")] + ["parent_run_id"]:
        st.session_state.pop(key, None)
    st.switch_page("app_pages/1_Research_Workspace.py")


def open_run(run_id: str) -> None:
    select_run(run_id)
    st.switch_page("app_pages/3_Research_Results.py")


def initials(name: str) -> str:
    parts = [p for p in name.replace("@", " ").split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def profile_block(user: CurrentUser) -> None:
    """Avatar, name and plan, plus sign-in / sign-out (only when login is configured)."""
    if not user.auth_enabled:
        plan = "Local mode · admin"
    elif user.is_guest:
        plan = "Demo mode only"
    else:
        plan = user.email or "Signed in"
    avatar = (f'<img src="{escape(user.picture)}" alt="">' if user.picture and user.picture.startswith("https://")
              else escape(initials(user.name)))
    st.markdown(f'<div class="ds-profile"><div class="ds-avatar">{avatar}</div><div><b>{escape(user.name)}'
                f'{" · admin" if user.is_admin and user.auth_enabled else ""}</b><small>{escape(plan)}</small></div></div>',
                unsafe_allow_html=True)
    if not user.auth_enabled:
        return
    if user.is_guest:
        st.caption("Sign in to run live research on any question and keep a private history.")
        st.button("Sign in with Google", icon=":material/login:", on_click=login_google,
                  width="stretch", type="primary", key="side_signin")
    else:
        st.button("Sign out", icon=":material/logout:", on_click=st.logout, width="stretch", key="side_signout")


def sidebar() -> None:
    user = current_user()
    st.logo("assets/logo.svg", size="large", icon_image="assets/icon.svg")
    with st.sidebar:
        if st.button("New research", icon=":material/add:", key="side_new", width="stretch"):
            new_research()
        runs = [r for r in get_repo().list_runs(user.id, limit=6) if r.status != "running"][:3]
        if runs:
            st.markdown('<div class="ds-label" style="margin-top:14px">Recent research</div>', unsafe_allow_html=True)
            for run in runs:
                if st.button(run.question, key=f"recent_{run.id}", icon=":material/radio_button_checked:",
                             width="stretch", help=run.question):
                    open_run(run.id)
        st.divider()
        profile_block(user)
        with st.expander("Data & safety", icon=":material/lock:"):
            st.markdown(
                f"- Storage: {get_repo().storage_description}. Your runs, documents and activity are private to "
                "your account" + (" (guest data is temporary and removed after 24 h)" if user.is_guest else "") + ".\n"
                "- API keys are never stored in the database or shown in full.\n"
                "- Retrieved pages and uploads are treated as untrusted data; instructions inside them are ignored.\n"
                "- Agents can only call the configured search APIs and fetch public pages from search results.")
        st.caption(f"{APP_NAME} · verify important conclusions against the original sources.")
