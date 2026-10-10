"""Page 8: Settings. Providers, model, limits and output preferences (secrets are never stored or shown)."""
import pandas as pd
import streamlit as st

from src.config import get_settings, mask_secret
from src.models.research import DEPTH_PRESETS, Depth
from src.ui.components import page_header
from src.ui.state import effective_settings, get_repo, preference, provider_settings

repo = get_repo()
env = get_settings()
settings = effective_settings()
page_header("Configuration", "Settings", "Model, search providers, research limits and local data.")

st.subheader("Capabilities")
caps = st.columns(4)
caps[0].metric("LLM", "On" if settings.llm_configured else "Off", help=settings.openrouter_model if settings.llm_configured else "Set OPENROUTER_API_KEY")
caps[1].metric("Web search", "Tavily" if settings.web_search_configured else "Off")
caps[2].metric("Academic", "3 sources", help="OpenAlex, Crossref and arXiv (no key needed)")
caps[3].metric("Demo corpus", "Offline", help="Synthetic sources, used only on the Demo page")
with st.expander("Data & safety", icon=":material/lock:"):
    st.markdown(
        f"- Accounts, runs, sources and reports are stored locally in `{settings.db_path.name}` (SQLite). Each run "
        "belongs to the account that started it, and only that account can open or delete it.\n"
        "- Passwords are stored only as salted scrypt hashes. Google and Microsoft sign-in store no password.\n"
        "- API keys are read from `.env` and are never stored or displayed in full "
        f"(OpenRouter: {mask_secret(settings.openrouter_api_key)}).\n"
        "- Retrieved pages and uploads are treated as untrusted data; instructions inside them are ignored.\n"
        "- Agents can only call the configured search APIs and fetch public pages from search results.")
st.caption("Appearance follows your Streamlit theme: choose Light, Dark or System from the ⋮ menu › Settings.")

st.subheader("API keys (read from .env)")
st.dataframe(pd.DataFrame([
    {"Setting": "OPENROUTER_API_KEY", "Status": mask_secret(env.openrouter_api_key), "Used for": "LLM planning, extraction, synthesis, Q&A"},
    {"Setting": "TAVILY_API_KEY", "Status": mask_secret(env.tavily_api_key), "Used for": "Live web and news search"},
    {"Setting": "CONTACT_EMAIL", "Status": "set" if env.contact_email else "not set", "Used for": "Polite use of OpenAlex/Crossref APIs"},
]), hide_index=True, width="stretch")
st.caption("To change keys, edit `.env` in the project folder and restart the app. Keys are never written to the "
           "database or shown in full.")

st.subheader("LLM")
with st.form("llm"):
    st.text_input("Provider endpoint", value=env.openrouter_base_url, disabled=True,
                  help="Set OPENROUTER_BASE_URL in .env to change it.")
    model = st.text_input("Model (OpenRouter id)", value=settings.openrouter_model,
                          help="Any OpenRouter model that supports JSON output, e.g. openai/gpt-4o-mini.")
    if st.form_submit_button("Save model"):
        repo.set_setting("llm_model", model.strip() or env.openrouter_model)
        st.success("Saved.")
st.caption("OpenRouter is used only for language tasks. It does not perform web searches; source discovery is "
           "handled separately by the search providers below.")

st.subheader("Search providers (live mode)")
current = provider_settings()
with st.form("providers"):
    tavily = st.checkbox("Tavily web & news search", value=current.tavily, disabled=not env.web_search_configured,
                         help=None if env.web_search_configured else "Requires TAVILY_API_KEY")
    openalex = st.checkbox("OpenAlex (scholarly works)", value=current.openalex)
    crossref = st.checkbox("Crossref (DOI metadata, lead resolution)", value=current.crossref)
    arxiv = st.checkbox("arXiv (preprints)", value=current.arxiv)
    fetch = st.checkbox("Fetch full text of web results (bounded, public pages only)", value=current.fetch_full_text)
    if st.form_submit_button("Save providers"):
        repo.set_setting("providers", {"tavily": tavily, "openalex": openalex, "crossref": crossref, "arxiv": arxiv,
                                       "fetch_full_text": fetch})
        st.success("Saved.")
st.caption("The Demo page always uses the offline synthetic corpus, whatever the settings here.")

st.subheader("Research defaults and limits")
with st.form("defaults"):
    depth = st.selectbox("Default depth", [d.value for d in Depth], index=[d.value for d in Depth].index(preference("depth")))
    iterations = st.slider("Default maximum follow-up rounds", 1, 6, int(preference("max_iterations")))
    banner = st.checkbox("Add a 'synthetic demo' banner to exported demo reports", value=bool(preference("include_demo_banner")))
    if st.form_submit_button("Save defaults"):
        for key, value in {"depth": depth, "max_iterations": iterations, "include_demo_banner": banner}.items():
            repo.set_setting(f"pref_{key}", value)
        st.success("Saved.")
st.dataframe(pd.DataFrame([{
    "Depth": d.value, "Subquestions": p["subquestions"], "Queries / subquestion": p["queries_per_subquestion"],
    "Results / search": p["results_per_search"], "Max searches": p["budget"].max_searches,
    "Max sources": p["budget"].max_sources, "Max seconds": p["budget"].max_seconds,
    "Max LLM calls": p["budget"].max_llm_calls, "Max LLM tokens": p["budget"].max_llm_tokens}
    for d, p in DEPTH_PRESETS.items()]), hide_index=True, width="stretch")
st.caption("Hard limits per depth. The orchestrator also stops early when evidence is sufficient or new rounds stop "
           "finding new sources.")

st.subheader("Data")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"Database: `{settings.db_path}`")
    st.markdown(f"Cached search results: **{repo.cache_size()}** (valid for 24 h)")
    if st.button("Clear search cache"):
        st.success(f"Removed {repo.clear_cache()} cached result(s).")
with c2:
    docs = repo.list_documents()
    st.markdown(f"Uploaded documents: **{len(docs)}**")
    for doc in docs:
        cols = st.columns([4, 1])
        cols[0].caption(f"{doc['title'][:60]} ({doc['filename']}, {doc['sections']} sections)")
        if cols[1].button("Delete", key=f"doc_{doc['id']}"):
            repo.delete_document(doc["id"])
            st.rerun()
