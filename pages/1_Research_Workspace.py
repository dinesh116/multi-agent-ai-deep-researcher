"""Page 1: Research Workspace. Define an investigation and start it."""
from datetime import date

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from src.ingestion.extract import ALLOWED_UPLOADS, ExtractionError, extract_upload
from src.models.research import DEPTH_PRESETS, Depth, ResearchMode, ResearchRequest, SourcePreference
from src.ui.components import page_header
from src.ui.state import effective_settings, get_repo, preference, select_run

repo, settings = get_repo(), effective_settings()
page_header("Research", "Research Workspace", "Ask a complex question. Sensible defaults are set, so you can just type and run.")

EXAMPLES = [
    "How will agentic AI transform enterprise software over the next five years?",
    "What are the competitive advantages and risks of AI-native startups?",
    "How are major payment companies adopting generative AI?",
    "What evidence supports or contradicts the claim that AI agents will replace traditional SaaS workflows?",
    "Which emerging technologies could create new business opportunities in India?",
    "What are the latest research developments in retrieval-augmented generation?",
]

draft = st.session_state.pop("refine_draft", None)
if draft:
    st.session_state["q_text"] = draft["question"]
    st.session_state["q_context"] = draft["context"]
    st.session_state["parent_run_id"] = draft["parent_run_id"]
    st.info("Refining a previous investigation: its findings are included as background context.", icon=":material/replay:")

with st.expander("Example questions", expanded=not st.session_state.get("q_text")):
    cols = st.columns(2)
    for i, example in enumerate(EXAMPLES):
        if cols[i % 2].button(example, key=f"ex_{i}", width="stretch"):
            st.session_state["q_text"] = example
            st.rerun()

question = st.text_area("Research question", key="q_text", height=80, max_chars=600,
                        placeholder="e.g. How will agentic AI transform enterprise software over the next five years?")
with st.expander("Background context and objectives (optional)"):
    context = st.text_area("Background context", key="q_context", height=100, max_chars=4000,
                           help="What you already know, what decision this informs, or constraints. Used for planning.")
    objectives_text = st.text_area("Research objectives (one per line)", key="q_objectives", height=80)

c1, c2, c3 = st.columns([2, 2, 1.4])
depth_options = [d.value for d in Depth]
depth = c1.segmented_control("Investigation depth", depth_options, default=preference("depth"),
                             format_func=lambda d: {"quick": "Quick", "standard": "Standard", "deep": "Deep"}[d],
                             key="q_depth") or "standard"
preset = DEPTH_PRESETS[Depth(depth)]
c1.caption(f"{preset['subquestions']} subquestions · up to {preset['budget'].max_searches} searches · "
           f"{preset['budget'].max_sources} sources · {preset['budget'].max_seconds // 60} min")
max_iter = c2.slider("Maximum follow-up rounds", 1, 6, value=int(preference("max_iterations")), key="q_iter",
                     help="Bounded research loop: the orchestrator may stop earlier if evidence is sufficient.")
mode = c3.radio("Mode", [m.value for m in ResearchMode], index=0 if preference("mode") == "demo" else 1,
                format_func=lambda m: "Demo (offline, synthetic)" if m == "demo" else "Live research",
                key="q_mode")

pref_labels = {SourcePreference.WEB: "Web", SourcePreference.ACADEMIC: "Academic papers", SourcePreference.NEWS: "News",
               SourcePreference.OFFICIAL: "Official / regulatory", SourcePreference.UPLOADED: "My documents",
               SourcePreference.DATASET: "Datasets"}
prefs = st.pills("Source types", list(pref_labels), default=[p for p in pref_labels if p != SourcePreference.DATASET],
                 selection_mode="multi", format_func=lambda p: pref_labels[p], key="q_prefs")

d1, d2, d3 = st.columns([1, 1.5, 1.5])
use_dates = d1.checkbox("Limit publication dates", key="q_use_dates")
date_from = d2.date_input("From", value=date(date.today().year - 3, 1, 1), disabled=not use_dates, key="q_from")
date_to = d3.date_input("To", value=date.today(), disabled=not use_dates, key="q_to")

if mode == ResearchMode.LIVE.value:
    notes = []
    if not settings.web_search_configured:
        notes.append("Web/news search is off (no `TAVILY_API_KEY`). Academic sources and uploads remain available.")
    if not settings.llm_configured:
        notes.append("No `OPENROUTER_API_KEY`: agents use deterministic logic (no LLM planning or synthesis).")
    for note in notes:
        st.caption(note)
    use_llm = st.toggle("Use LLM for planning, extraction and synthesis", value=settings.llm_configured,
                        disabled=not settings.llm_configured, key="q_llm")
else:
    use_llm = False
    st.caption("Demo mode searches a bundled SYNTHETIC corpus offline with deterministic agents. Nothing is sent "
               "over the network.")

with st.expander("Your documents (PDF, TXT, Markdown, CSV)"):
    uploads = st.file_uploader("Add documents to the research corpus", type=[e.lstrip(".") for e in ALLOWED_UPLOADS],
                               accept_multiple_files=True, key=f"uploader_{st.session_state.get('up_round', 0)}")
    if uploads and st.button("Add uploaded files"):
        for file in uploads:
            try:
                doc = extract_upload(file.name, file.getvalue(), settings.max_upload_bytes)
                doc_id, created = repo.save_document(file.name, doc.title, doc.kind, file.getvalue(), doc.sections,
                                                     doc.warnings)
                st.success(f"{file.name}: {'added' if created else 'already in your library'} "
                           f"({len(doc.sections)} sections)")
            except ExtractionError as exc:
                st.error(str(exc))
        st.session_state["up_round"] = st.session_state.get("up_round", 0) + 1
    library = repo.list_documents()
    selected_docs = st.multiselect("Include these documents", [d["id"] for d in library],
                                   format_func=lambda i: next(f"{d['title'][:60]} ({d['filename']})" for d in library
                                                              if d["id"] == i), key="q_docs")

if st.button("Run research", icon=":material/play_arrow:", type="primary", width="stretch"):
    try:
        request = ResearchRequest(
            question=question or "", context=context, depth=Depth(depth), max_iterations=max_iter, mode=ResearchMode(mode),
            objectives=[o for o in (objectives_text or "").splitlines() if o.strip()],
            source_preferences=list(prefs or [SourcePreference.WEB, SourcePreference.ACADEMIC]),
            date_from=date_from if use_dates else None, date_to=date_to if use_dates else None, use_llm=use_llm,
            document_ids=selected_docs, parent_run_id=st.session_state.get("parent_run_id"))
    except ValidationError as exc:
        for error in exc.errors():
            st.error(error["msg"].removeprefix("Value error, "))
        st.stop()
    st.session_state["pending_request"] = request.model_dump_json()
    st.session_state.pop("parent_run_id", None)
    st.switch_page("pages/2_Research_Progress.py")

st.subheader("Recent research")
runs = repo.list_runs(limit=6)
if not runs:
    st.caption("No investigations yet.")
for run in runs:
    with st.container(border=True):
        left, right = st.columns([5, 1])
        left.markdown(f"**{run.question}**")
        left.caption(f"{run.created_at:%d %b %Y %H:%M} · {'demo' if run.mode == 'demo' else 'live'} · {run.status} · "
                     f"{run.counts.get('sources', 0)} sources · {run.counts.get('claims', 0)} claims")
        if right.button("Open", key=f"open_{run.id}", disabled=run.status == "running"):
            select_run(run.id)
            st.switch_page("pages/6_Research_Report.py")
