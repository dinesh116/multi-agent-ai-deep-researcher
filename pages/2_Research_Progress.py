"""Page 2: Research Progress. Live workflow events from the orchestrator, or the audit trail of a past run."""
import queue
import threading
import time

import pandas as pd
import streamlit as st

from src.models.evidence import AgentEvent
from src.models.research import ResearchRequest, new_id
from src.orchestration.state import AGENT_ORDER
from src.services.research_service import run_research
from src.ui.components import AGENT_TITLES, STATUS_ICON, demo_banner, page_header
from src.ui.state import (current_user, effective_settings, get_repo, load_selected_run, provider_settings,
                         select_run)

repo = get_repo()
page_header("Orchestration", "Research Progress", "Live workflow events from the LangGraph orchestrator, and the audit trail of each run.")


def stage_table(statuses: dict[str, str], current: str | None) -> pd.DataFrame:
    return pd.DataFrame([{"": STATUS_ICON.get(statuses.get(a, "pending"), "○"), "Agent": AGENT_TITLES[a],
                          "Status": ("running" if a == current and statuses.get(a) != "completed" else statuses.get(a, "pending"))}
                         for a in AGENT_ORDER])


def event_rows(events: list[AgentEvent]) -> pd.DataFrame:
    return pd.DataFrame([{"Time": e.timestamp.strftime("%H:%M:%S"), "Agent": AGENT_TITLES.get(e.agent, e.agent),
                          "Event": e.status, "Iteration": e.iteration, "Message": e.message} for e in events])


pending = st.session_state.pop("pending_request", None)
if pending:
    request = ResearchRequest.model_validate_json(pending)
    owner_id = current_user().id
    run_id = new_id("run")
    events: "queue.Queue[AgentEvent]" = queue.Queue()
    outcome: dict = {}

    def worker() -> None:  # Streamlit UI calls must stay on the main thread, so the run reports via a queue
        try:
            outcome["state"] = run_research(request, effective_settings(), repo=repo, on_event=events.put,
                                            provider_settings=provider_settings(), run_id=run_id, owner_id=owner_id)
        except Exception as exc:  # surfaced below; the run row is marked failed by the service
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    st.markdown(f"**Investigating:** {request.question}")
    demo_banner(request.mode.value)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    statuses: dict[str, str] = {}
    current, subquestion = None, None
    counters = {"searches": 0, "new sources": 0, "claims": 0, "gaps": 0, "iteration": 0}
    log: list[AgentEvent] = []
    status_box = st.status("Research in progress…", expanded=True)
    with status_box:
        metrics_slot = st.empty()
        cols = st.columns([1.2, 2.8])
        stage_slot = cols[0].empty()
        log_slot = cols[1].empty()
    while thread.is_alive() or not events.empty():
        updated = False
        while not events.empty():
            event = events.get()
            log.append(event)
            updated = True
            if event.agent in AGENT_ORDER:
                if event.status == "started":
                    statuses[event.agent], current = "running", event.agent
                elif event.status in ("completed", "decision"):
                    statuses[event.agent] = "completed"
                elif event.status == "failed":
                    statuses[event.agent] = "failed"
            counters["iteration"] = max(counters["iteration"], event.iteration)
            if event.status == "search":
                counters["searches"] += 1
                subquestion = event.metrics.get("subquestion") or subquestion
            counters["new sources"] = max(counters["new sources"], event.metrics.get("total_sources", 0))
            counters["claims"] = event.metrics.get("claims", counters["claims"])
            counters["gaps"] = event.metrics.get("gaps", counters["gaps"])
        if updated:
            with metrics_slot.container():
                m = st.columns(6)
                m[0].metric("Current agent", AGENT_TITLES.get(current or "", "—"))
                m[1].metric("Subquestion", subquestion or "—")
                m[2].metric("Searches", counters["searches"])
                m[3].metric("Sources", counters["new sources"])
                m[4].metric("Claims", counters["claims"])
                m[5].metric("Follow-up round", counters["iteration"])
            stage_slot.dataframe(stage_table(statuses, current), hide_index=True, width="stretch")
            log_slot.dataframe(event_rows(log[-14:][::-1]), hide_index=True, width="stretch", height=380)
        time.sleep(0.15)
    thread.join()

    state = outcome.get("state")
    if state and state.get("report"):
        status_box.update(label=f"Research complete in {state['usage'].elapsed_seconds}s", state="complete", expanded=False)
        select_run(run_id)
        st.success(f"Done: {len(state['sources'])} sources, {len(state['claims'])} claims, "
                   f"{len(state['contradictions'])} contradiction(s), {len(state['insights'])} insights. "
                   f"Stopped because: {state.get('stop_reason') or 'workflow finished'}")
        c = st.columns(3)
        c[0].page_link("pages/6_Research_Report.py", label="Read the report", icon=":material/description:")
        c[1].page_link("pages/3_Evidence_Explorer.py", label="Explore the evidence", icon=":material/library_books:")
        c[2].page_link("pages/4_Critical_Analysis.py", label="See the critical analysis", icon=":material/balance:")
    else:
        status_box.update(label="Research failed", state="error")
        st.error(outcome.get("error") or "The workflow finished without a report. See errors below.")
        if state:
            select_run(run_id)
    for error in (state or {}).get("errors", []):
        st.error(error)
    st.stop()

# ------------------------------------------------------------------------------ audit trail of the selected run
bundle = load_selected_run()
if bundle is None:
    st.info("No investigation is running. Start one in the Research Workspace.", icon=":material/info:")
    st.page_link("pages/1_Research_Workspace.py", label="Go to Research Workspace", icon=":material/arrow_forward:")
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
