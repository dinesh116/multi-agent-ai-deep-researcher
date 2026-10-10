"""Shared UI state: identity (login / guest), repository, settings, selected run and sidebar.

Identity:
- If Google sign-in is configured ([auth] in Streamlit secrets), signed-in users are identified by their stable
  provider subject id; visitors who are not signed in get a temporary per-session guest id (demo mode only).
- Without [auth] (local use), there is a single "local" user who is also the admin.
Every repository call passes the current user's id, so data is private per user.
"""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass

import streamlit as st

from src.config import APP_NAME, Settings, get_settings, mask_secret
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

    @property
    def can_use_live(self) -> bool:
        return not self.is_guest


@st.cache_resource
def get_repo() -> Repository:
    settings = get_settings()
    repo = Repository(settings.db_path, settings.turso_database_url, settings.turso_auth_token)
    repo.mark_stale_runs()
    repo.purge_guest_data()
    return repo


def auth_enabled() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:  # no secrets file at all
        return False


def current_user() -> CurrentUser:
    settings = get_settings()
    if not auth_enabled():
        return CurrentUser(LOCAL_OWNER, None, "Local user", is_guest=False, is_admin=True, auth_enabled=False)
    if st.user.get("is_logged_in", False):  # st.user may lack the attribute before auth initialises
        user_id = str(st.user.get("sub") or st.user.get("email"))
        email = (st.user.get("email") or "").lower() or None
        if st.session_state.get("_user_recorded") != user_id:  # once per session: profile + login activity
            repo = get_repo()
            repo.upsert_user(user_id, email, st.user.get("name"), st.user.get("picture"), provider="google")
            repo.log_activity(user_id, "login", detail={"email": email})
            st.session_state["_user_recorded"] = user_id
        return CurrentUser(user_id, email, st.user.get("name") or email or "Signed-in user", is_guest=False,
                           is_admin=bool(email and email in settings.admin_emails), auth_enabled=True)
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
        st.info("No research run selected yet. Start an investigation in the **Research Workspace**, or open one "
                "from **Research History**.", icon=":material/info:")
        st.page_link("pages/1_Research_Workspace.py", label="Go to Research Workspace", icon=":material/arrow_forward:")
        st.stop()
    return bundle


def account_block(user: CurrentUser) -> None:
    """Sign-in / sign-out controls (only when login is configured)."""
    if not user.auth_enabled:
        return
    if user.is_guest:
        st.markdown("**Guest** · demo mode only")
        st.caption("Sign in to run live research and keep a private history.")
        st.button("Sign in with Google", icon=":material/login:", on_click=st.login, args=("google",),
                  width="stretch", type="primary")
    else:
        st.markdown(f"**{user.name}**" + (" · admin" if user.is_admin else ""))
        if user.email:
            st.caption(user.email)
        st.button("Sign out", icon=":material/logout:", on_click=st.logout, width="stretch")
    st.divider()


def sidebar() -> None:
    settings = effective_settings()
    user = current_user()
    with st.sidebar:
        account_block(user)
        bundle = load_selected_run()
        if bundle:
            st.caption("Current investigation")
            st.markdown(f"**{bundle.summary.question[:110]}**")
            mode = "Demo (synthetic)" if bundle.summary.mode == "demo" else "Live research"
            st.caption(f"{mode} · {bundle.summary.created_at:%d %b %Y %H:%M} · {bundle.summary.status}")
        st.divider()
        st.caption("Capabilities")

        def row(label: str, on: bool, value: str) -> str:
            return (f'<div class="dr-cap"><span class="dr-dot {"on" if on else "off"}"></span>'
                    f'<span class="dr-cap-k">{label}</span><span class="dr-cap-v">{value}</span></div>')
        st.markdown(
            row("LLM", settings.llm_configured, settings.openrouter_model if settings.llm_configured else "not configured")
            + row("Web search", settings.web_search_configured, "Tavily" if settings.web_search_configured else "not configured")
            + row("Academic", True, "OpenAlex · Crossref · arXiv")
            + row("Demo corpus", True, "offline · synthetic"), unsafe_allow_html=True)
        with st.expander("Data & safety", icon=":material/lock:"):
            st.markdown(
                f"- Storage: {get_repo().storage_description}. Your runs, documents and activity are private to "
                "your account" + (" (guest data is temporary and removed after 24 h)" if user.is_guest else "") + ".\n"
                "- API keys are read from `.env` and are never stored or displayed in full "
                f"(OpenRouter: {mask_secret(settings.openrouter_api_key)}).\n"
                "- Retrieved pages and uploads are treated as untrusted data; instructions inside them are ignored.\n"
                "- Agents can only call the configured search APIs and fetch public pages from search results.")
        st.caption(f"{APP_NAME} · research assistant. Verify important conclusions against the original sources.")
