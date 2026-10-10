"""Shared UI state: repository, settings, provider configuration, the signed-in user, selected run and sidebar."""
from __future__ import annotations

import dataclasses
from html import escape

import streamlit as st

from src.auth.session import SESSION_KEY, sign_out
from src.config import Settings, get_settings
from src.database.repository import Repository
from src.models.run import RunBundle
from src.models.user import User
from src.search.registry import ProviderSettings
from src.ui.theme import active_theme

DEFAULTS = {"depth": "standard", "max_iterations": 2, "use_llm": True, "include_demo_banner": True}


@st.cache_resource
def get_repo() -> Repository:
    repo = Repository(get_settings().db_path)
    repo.mark_stale_runs()
    return repo


def effective_settings() -> Settings:
    """Environment settings plus the user's non-secret overrides (e.g. model name)."""
    settings = get_settings()
    model = get_repo().get_setting("llm_model")
    return dataclasses.replace(settings, openrouter_model=model) if model else settings


def provider_settings() -> ProviderSettings:
    stored = get_repo().get_setting("providers", {})
    return ProviderSettings(**{k: v for k, v in stored.items() if k in ProviderSettings.__dataclass_fields__})


def preference(key: str):
    return get_repo().get_setting(f"pref_{key}", DEFAULTS[key])


# ---------------------------------------------------------------------- signed-in user
def current_user_id() -> str | None:
    return st.session_state.get(SESSION_KEY)


def require_user() -> User:
    """The signed-in user (app.py only shows pages to signed-in users, so this is always set there)."""
    user = get_repo().get_user(current_user_id() or "")
    if user is None:
        st.session_state.clear()
        st.rerun()
    return user


# ---------------------------------------------------------------------- selected run (always one of the user's own)
def selected_run_id() -> str | None:
    run_id = st.session_state.get("selected_run_id")
    if run_id:
        return run_id
    runs = [r for r in get_repo().list_runs(limit=5, user_id=current_user_id()) if r.status == "completed"]
    return runs[0].id if runs else None


def load_selected_run() -> RunBundle | None:
    run_id = selected_run_id()
    if not run_id:
        return None
    cache = st.session_state.setdefault("_bundle_cache", {})
    if run_id not in cache:
        bundle = get_repo().load_run(run_id)
        if bundle is None or bundle.summary.user_id != current_user_id():  # missing, or another user's run
            st.session_state.pop("selected_run_id", None)
            return None
        cache.clear()
        cache[run_id] = bundle
    return cache[run_id]


def select_run(run_id: str) -> None:
    st.session_state["selected_run_id"] = run_id
    st.session_state.pop("_bundle_cache", None)


def require_run() -> RunBundle:
    bundle = load_selected_run()
    if bundle is None:
        st.info("No research run selected yet. Start an investigation in **New research**, or open one from "
                "**My research runs**.", icon=":material/info:")
        st.page_link("pages/1_Research_Workspace.py", label="Start new research", icon=":material/arrow_forward:")
        st.stop()
    return bundle


# ---------------------------------------------------------------------- sidebar footer (the menu itself is st.navigation)
def sidebar(user: User) -> None:
    with st.sidebar:
        bundle = load_selected_run()
        if bundle:
            st.caption("Current investigation")
            st.markdown(f"**{escape(bundle.summary.question[:110])}**")
            mode = "Demo (synthetic)" if bundle.summary.mode == "demo" else "Live research"
            st.caption(f"{mode} · {bundle.summary.created_at:%d %b %Y %H:%M} · {bundle.summary.status}")
            st.divider()
        st.markdown(f'<div class="dr-user"><div class="dr-avatar" aria-hidden="true">{escape(user.initials)}</div>'
                    f'<div><b>{escape(user.name)}</b><span>Signed in with {escape(user.provider_label)}</span></div></div>',
                    unsafe_allow_html=True)
        if st.button("Sign out", icon=":material/logout:", width="stretch", key="sign_out"):
            sign_out()
        st.caption(f"{active_theme().title()} theme · switch Light, Dark or System in ⋮ › Settings.")
