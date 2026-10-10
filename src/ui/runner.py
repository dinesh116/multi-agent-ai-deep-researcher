"""Runs an investigation in a worker thread and renders its live progress (shared by Progress and Demo pages)."""
from __future__ import annotations

import queue
import threading
import time

import pandas as pd
import streamlit as st

from src.models.evidence import AgentEvent
from src.models.research import ResearchRequest, new_id
from src.orchestration.state import AGENT_ORDER
from src.services.research_service import run_research
from src.ui.components import AGENT_TITLES, STATUS_ICON
from src.ui.state import current_user_id, effective_settings, get_repo, provider_settings, select_run


def stage_table(statuses: dict[str, str], current: str | None) -> pd.DataFrame:
    return pd.DataFrame([{"": STATUS_ICON.get(statuses.get(a, "pending"), "○"), "Agent": AGENT_TITLES[a],
                          "Status": ("running" if a == current and statuses.get(a) != "completed" else statuses.get(a, "pending"))}
                         for a in AGENT_ORDER])


def event_rows(events: list[AgentEvent]) -> pd.DataFrame:
    return pd.DataFrame([{"Time": e.timestamp.strftime("%H:%M:%S"), "Agent": AGENT_TITLES.get(e.agent, e.agent),
                          "Event": e.status, "Iteration": e.iteration, "Message": e.message} for e in events])


def run_with_progress(request: ResearchRequest) -> dict | None:
    """Execute `request` for the signed-in user, streaming orchestrator events into the page. Returns the final state."""
    repo, user_id = get_repo(), current_user_id()
    run_id = new_id("run")
    events: "queue.Queue[AgentEvent]" = queue.Queue()
    outcome: dict = {}
    settings, providers = effective_settings(), provider_settings()

    def worker() -> None:  # Streamlit UI calls must stay on the main thread, so the run reports via a queue
        try:
            outcome["state"] = run_research(request, settings, repo=repo, on_event=events.put,
                                            provider_settings=providers, run_id=run_id, user_id=user_id)
        except Exception as exc:  # surfaced below; the run row is marked failed by the service
            outcome["error"] = f"{type(exc).__name__}: {exc}"

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
    return state
