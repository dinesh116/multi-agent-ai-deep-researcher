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
    model = st.text_input("Main model (planning, research strategy, synthesis)", value=settings.openrouter_model,
                          help="Any OpenRouter model that supports JSON output, e.g. openai/gpt-4o.")
    fast = st.text_input("Fast model (high-volume extraction and checks)", value=settings.fast_model,
                         help="A cheaper model used for claim/number/entity extraction and verification, "
                              "e.g. openai/gpt-4o-mini. Set it to the same id to use one model for everything.")
    if st.form_submit_button("Save models"):
        repo.set_setting("llm_model", model.strip() or env.openrouter_model)
        repo.set_setting("llm_fast_model", fast.strip() or model.strip() or env.openrouter_model)
        st.success("Saved.")
st.caption("OpenRouter is used only for language tasks. It does not perform web searches; source discovery is "
           "handled separately by the search providers below.")

st.subheader("Search providers (live mode)")
current = provider_settings()
with st.form("providers"):
    tavily = st.checkbox("Tavily web & news search", value=current.tavily, disabled=not env.web_search_configured,
                         help=None if env.web_search_configured else "Requires TAVILY_API_KEY")
    advanced = st.checkbox("Tavily advanced search with full page content (≈2 credits per search)",
                           value=current.tavily_advanced, disabled=not env.web_search_configured)
    openalex = st.checkbox("OpenAlex (scholarly works, citation snowballing)", value=current.openalex)
    semantic = st.checkbox("Semantic Scholar (citations, TLDRs, open-access PDFs)", value=current.semantic_scholar)
    crossref = st.checkbox("Crossref (DOI metadata, lead resolution)", value=current.crossref)
    arxiv = st.checkbox("arXiv (preprints)", value=current.arxiv)
    fetch = st.checkbox("Fetch full texts: web pages and open-access PDFs (bounded, public hosts only)",
                        value=current.fetch_full_text)
    if st.form_submit_button("Save providers"):
        repo.set_setting("providers", {"tavily": tavily, "tavily_advanced": advanced, "openalex": openalex,
                                       "semantic_scholar": semantic, "crossref": crossref, "arxiv": arxiv,
                                       "fetch_full_text": fetch})
        st.success("Saved.")
st.caption("Demo mode always uses the offline synthetic corpus, whatever the settings here.")

st.subheader("Research defaults and limits")
with st.form("defaults"):
    depth = st.selectbox("Default depth", [d.value for d in Depth], index=[d.value for d in Depth].index(preference("depth")))
    iterations = st.slider("Default maximum follow-up rounds", 1, 6, int(preference("max_iterations")))
    mode = st.radio("Default mode", ["demo", "live"], index=0 if preference("mode") == "demo" else 1, horizontal=True)
    banner = st.checkbox("Add a 'synthetic demo' banner to exported demo reports", value=bool(preference("include_demo_banner")))
    if st.form_submit_button("Save defaults"):
        for key, value in {"depth": depth, "max_iterations": iterations, "mode": mode, "include_demo_banner": banner}.items():
            repo.set_setting(f"pref_{key}", value)
        st.success("Saved.")
st.dataframe(pd.DataFrame([{
    "Depth": d.value, "Subquestions": p["subquestions"], "Queries / subquestion": p["queries_per_subquestion"],
    "Results / search": p["results_per_search"], "Full texts / round": p["full_text_fetches"],
    "LLM windows / source": p["llm_windows_per_source"], "Max searches": p["budget"].max_searches,
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
