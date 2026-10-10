"""Shared UI state: repository, settings, provider configuration, selected run and sidebar."""
from __future__ import annotations

import dataclasses

import streamlit as st

from src.config import APP_NAME, Settings, get_settings, mask_secret
from src.database.repository import Repository
from src.models.run import RunBundle
from src.search.registry import ProviderSettings

DEFAULTS = {"depth": "standard", "max_iterations": 2, "mode": "demo", "use_llm": True, "include_demo_banner": True}


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


def selected_run_id() -> str | None:
    run_id = st.session_state.get("selected_run_id")
    if run_id:
        return run_id
    runs = [r for r in get_repo().list_runs(limit=5) if r.status == "completed"]
    return runs[0].id if runs else None


def load_selected_run() -> RunBundle | None:
    run_id = selected_run_id()
    if not run_id:
        return None
    cache = st.session_state.setdefault("_bundle_cache", {})
    if run_id not in cache:
        bundle = get_repo().load_run(run_id)
        if bundle is None:
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
        st.info("No research run selected yet. Start an investigation in the **Research Workspace**, or open one "
                "from **Research History**.", icon=":material/info:")
        st.page_link("pages/1_Research_Workspace.py", label="Go to Research Workspace", icon=":material/arrow_forward:")
        st.stop()
    return bundle


def sidebar() -> None:
    settings = effective_settings()
    with st.sidebar:
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
                f"- Runs, sources and reports are stored locally in `{settings.db_path.name}` (SQLite).\n"
                "- API keys are read from `.env` and are never stored or displayed in full "
                f"(OpenRouter: {mask_secret(settings.openrouter_api_key)}).\n"
                "- Retrieved pages and uploads are treated as untrusted data; instructions inside them are ignored.\n"
                "- Agents can only call the configured search APIs and fetch public pages from search results.")
        st.caption(f"{APP_NAME} · research assistant. Verify important conclusions against the original sources.")
