"""Page 2: Research Progress. Live workflow events from the orchestrator, or the audit trail of a past run."""
import pandas as pd
import streamlit as st

from src.models.research import ResearchRequest
from src.ui.components import AGENT_TITLES, STATUS_ICON, demo_banner, page_header
from src.ui.runner import event_rows, run_with_progress
from src.ui.state import load_selected_run

page_header("Orchestration", "Research Progress", "Live workflow events from the LangGraph orchestrator, and the audit trail of each run.")

pending = st.session_state.pop("pending_request", None)
if pending:
    request = ResearchRequest.model_validate_json(pending)
    st.markdown(f"**Investigating:** {request.question}")
    demo_banner(request.mode.value)
    run_with_progress(request)
    st.stop()

# ------------------------------------------------------------------------------ audit trail of the selected run
bundle = load_selected_run()
if bundle is None:
    st.info("No investigation is running. Start one from New research.", icon=":material/info:")
    st.page_link("pages/1_Research_Workspace.py", label="Start new research", icon=":material/arrow_forward:")
    st.stop()

st.markdown(f"**Investigation:** {bundle.summary.question}")
st.caption(f"Run {bundle.summary.id} · {bundle.summary.status} · started {bundle.summary.created_at:%d %b %Y %H:%M}. "
           "These are the events recorded by the orchestrator during the run.")
demo_banner(bundle.summary.mode)
usage = bundle.usage
if usage:
    m = st.columns(7)
    m[0].metric("Rounds", usage.iterations + 1)
    m[1].metric("Searches", usage.searches)
    m[2].metric("Cache hits", usage.cache_hits)
    m[3].metric("Sources", len(bundle.sources))
    m[4].metric("Claims", len(bundle.claims))
    m[5].metric("LLM calls", usage.llm_calls, help=f"{usage.llm_tokens:,} tokens (as reported by the provider)")
    m[6].metric("Duration", f"{usage.elapsed_seconds}s")
    if usage.exhausted:
        st.warning("Limits reached: " + ", ".join(usage.exhausted), icon="⏱️")
st.markdown(f"**Stopping decision:** {bundle.stop_reason or '—'}")
for note in bundle.provider_notes:
    st.info(note, icon="ℹ️")

left, right = st.columns([1.3, 2.7])
with left:
    st.subheader("Agents")
    st.dataframe(pd.DataFrame([{"": STATUS_ICON.get(s.status, "○"), "Agent": AGENT_TITLES.get(a, a), "Runs": s.runs,
                                "Time (ms)": s.duration_ms} for a, s in bundle.statuses.items()]),
                 hide_index=True, width="stretch")
    open_gaps = [g for g in bundle.gaps if g.expected_value >= 0.35]
    st.metric("Unresolved gaps", len(open_gaps))
with right:
    st.subheader("Event log")
    st.dataframe(event_rows(bundle.events), hide_index=True, width="stretch", height=420)

st.subheader("Search activity")
if bundle.search_log:
    st.dataframe(pd.DataFrame([{"Round": r["iteration"], "Subquestion": r.get("subquestion_id") or "—",
                                "Provider": r["provider"], "Query": r["query"], "Status": r["status"],
                                "Results": r["results"], "New sources": r["new_sources"], "Note": r.get("message", "")}
                               for r in bundle.search_log]), hide_index=True, width="stretch")
for warning in dict.fromkeys(bundle.warnings):
    st.warning(warning)
for error in bundle.errors:
    st.error(error)
