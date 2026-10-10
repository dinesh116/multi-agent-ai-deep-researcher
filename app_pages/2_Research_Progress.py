"""Page 2: Agents in action. Live workflow events from the orchestrator, or the audit trail of a past run."""
import queue
import threading
import time
from html import escape

import pandas as pd
import streamlit as st

from src.models.evidence import AgentEvent
from src.models.research import ResearchRequest, new_id
from src.orchestration.state import AGENT_ORDER
from src.services.research_service import run_research
from src.ui.components import AGENT_INFO, AGENT_TITLES, DEPTH_LABELS, card, demo_banner, eyebrow, html
from src.ui.state import (current_user, effective_settings, get_repo, load_selected_run, new_research, open_run,
                         provider_settings, select_run)

repo = get_repo()
STATE_LABEL = {"completed": "✓ Complete", "running": "◌ Working", "failed": "✕ Failed"}
ROW_CLASS = {"completed": "done", "running": "working", "failed": "failed"}


def heading(live: bool) -> None:
    left, right = st.columns([4, 1], vertical_alignment="center")
    left.markdown(eyebrow("Live investigation" if live else "Investigation log")
                  + '<div class="ds-title">Agents in <em>action</em></div><p class="ds-sub">'
                  + ("Your research team is working through the evidence." if live else
                     "What each agent did during this investigation, step by step.") + "</p>",
                  unsafe_allow_html=True)
    if live:
        right.markdown('<div style="text-align:right"><span class="ds-live"><i></i> LIVE</span></div>',
                       unsafe_allow_html=True)


def question_card(question: str, meta: list[str], done: int, caption: str) -> str:
    pct = int(round(100 * done / len(AGENT_ORDER)))
    spans = "".join(f"<span>{escape(m)}</span>" for m in meta)
    return (f'<div class="ds-card"><div class="ds-label">Research question</div>'
            f'<div style="font:600 17px Manrope,sans-serif;margin:6px 0 9px">{escape(question)}</div>'
            f'<div class="ds-meta">{spans}</div><div class="ds-progress"><i style="width:{pct}%"></i></div>'
            f'<div class="ds-progress-cap"><span>{escape(caption)}</span><b>{pct}%</b></div></div>')


def agents_card(statuses: dict[str, str], messages: dict[str, str], extra: dict[str, str] | None = None) -> str:
    rows = []
    for agent in AGENT_ORDER:
        icon, css, about = AGENT_INFO[agent]
        status = statuses.get(agent, "pending")
        note = messages.get(agent) or about
        state = (extra or {}).get(agent) or STATE_LABEL.get(status, "Queued")
        rows.append(f'<div class="ds-agent {ROW_CLASS.get(status, "")}"><span class="ds-icon {css}">{icon}</span>'
                    f'<div><b>{AGENT_TITLES[agent]}</b><small>{escape(note[:140])}</small></div>'
                    f'<span class="ds-state">{escape(state)}</span></div>')
    return (f'<div class="ds-card"><div style="display:flex;justify-content:space-between;align-items:center">'
            f'<b style="font:700 15px Manrope,sans-serif">Research team</b><span class="ds-muted">{len(AGENT_ORDER)} '
            f'agents</span></div>{"".join(rows)}</div>')


def activity_card(events: list[AgentEvent], running: bool) -> str:
    shown = [e for e in events if e.status not in ("search", "started")][-7:] or events[-7:]
    lines = []
    for i, e in enumerate(shown):
        current = " current" if running and i == len(shown) - 1 else ""
        title = f"{AGENT_TITLES.get(e.agent, e.agent)} · {e.status}"
        lines.append(f'<div class="ds-act{current}"><i></i><div><b>{escape(title)}</b>'
                     f'<small>{escape(e.message[:150])}</small><time>{e.timestamp:%H:%M:%S}</time></div></div>')
    body = "".join(lines) or '<div class="ds-muted" style="padding:10px 0">Waiting for the first agent…</div>'
    return (f'<div class="ds-card"><div style="display:flex;justify-content:space-between">'
            f'<b style="font:700 15px Manrope,sans-serif">Research activity</b>'
            f'<span style="color:#55b592">●</span></div>{body}</div>')


def track(event: AgentEvent, statuses: dict[str, str], messages: dict[str, str]) -> None:
    if event.agent not in AGENT_ORDER:
        return
    if event.status == "started":
        statuses[event.agent] = "running"
    elif event.status in ("completed", "decision"):
        statuses[event.agent] = "completed"
    elif event.status == "failed":
        statuses[event.agent] = "failed"
    if event.status != "started":
        messages[event.agent] = event.message


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

    heading(live=True)
    demo_banner(request.mode.value)
    meta = [f"✧ {DEPTH_LABELS[request.depth.value]} research", "Demo dataset" if request.mode.value == "demo"
            else "Live sources", "Started just now"]
    question_slot = st.empty()
    left, right = st.columns([1.5, 0.85])
    agents_slot, activity_slot = left.empty(), right.empty()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    statuses: dict[str, str] = {}
    messages: dict[str, str] = {}
    log: list[AgentEvent] = []
    sources = 0
    first = True
    while thread.is_alive() or not events.empty() or first:
        updated = first
        first = False
        while not events.empty():
            event = events.get()
            log.append(event)
            track(event, statuses, messages)
            sources = max(sources, event.metrics.get("total_sources", 0))
            updated = True
        if updated:
            done = sum(statuses.get(a) == "completed" for a in AGENT_ORDER)
            running = next((AGENT_TITLES[a] for a in AGENT_ORDER if statuses.get(a) == "running"), None)
            question_slot.markdown(question_card(request.question, meta + [f"{sources} sources found"], done,
                                                 f"{running} working" if running else "Starting the research team"),
                                   unsafe_allow_html=True)
            agents_slot.markdown(agents_card(statuses, messages), unsafe_allow_html=True)
            activity_slot.markdown(activity_card(log, running=True), unsafe_allow_html=True)
        time.sleep(0.15)
    thread.join()

    state = outcome.get("state")
    if state and state.get("report"):
        final = {a: ("completed" if statuses.get(a) == "completed" else statuses.get(a, "pending")) for a in AGENT_ORDER}
        question_slot.markdown(question_card(request.question, meta + [f"{len(state['sources'])} sources found"],
                                             len(AGENT_ORDER), f"Research complete in {state['usage'].elapsed_seconds}s"),
                               unsafe_allow_html=True)
        agents_slot.markdown(agents_card(final, messages, {a: "Skipped" for a in AGENT_ORDER if final[a] == "pending"}),
                             unsafe_allow_html=True)
        activity_slot.markdown(activity_card(log, running=False), unsafe_allow_html=True)
        select_run(run_id)
        st.success(f"Done: {len(state['sources'])} sources, {len(state['claims'])} claims, "
                   f"{len(state['contradictions'])} contradiction(s), {len(state['insights'])} insights. "
                   f"Stopped because: {state.get('stop_reason') or 'workflow finished'}")
        a, b = st.columns([3, 1])
        if a.button("New research", icon=":material/add:", key="after_new"):
            new_research()
        if b.button("View results →", type="primary", width="stretch", key="after_results"):
            open_run(run_id)
    else:
        st.error(outcome.get("error") or "The workflow finished without a report. See errors below.")
        if state:
            select_run(run_id)
    for error in (state or {}).get("errors", []):
        st.error(error)
    st.stop()

# ------------------------------------------------------------------------------ audit trail of the selected run
bundle = load_selected_run()
heading(live=False)
if bundle is None:
    st.info("No investigation is running. Start one in the Research workspace.", icon=":material/info:")
    if st.button("New research", icon=":material/add:", type="primary"):
        new_research()
    st.stop()

demo_banner(bundle.summary.mode)
statuses = {a: s.status for a, s in bundle.statuses.items()}
messages: dict[str, str] = {}
for event in bundle.events:
    if event.agent in AGENT_ORDER and event.status != "started":
        messages[event.agent] = event.message
extra = {a: f"✓ {s.runs}× · {s.duration_ms} ms" for a, s in bundle.statuses.items() if s.status == "completed"}
usage = bundle.usage
meta = [f"✧ {DEPTH_LABELS.get(bundle.summary.depth, 'Standard')} research",
        "Demo dataset" if bundle.summary.mode == "demo" else "Live sources",
        f"Started {bundle.summary.created_at:%d %b %Y %H:%M}", f"{len(bundle.sources)} sources found"]
html(question_card(bundle.summary.question, meta, sum(s == "completed" for s in statuses.values()),
                   f"Research {bundle.summary.status}" + (f" in {usage.elapsed_seconds}s" if usage else "")))
st.write("")
left, right = st.columns([1.5, 0.85])
left.markdown(agents_card(statuses, messages, extra), unsafe_allow_html=True)
right.markdown(activity_card(bundle.events, running=False), unsafe_allow_html=True)
st.write("")
if usage:
    with card("usage"):
        m = st.columns(7)
        m[0].metric("Rounds", usage.iterations + 1)
        m[1].metric("Searches", usage.searches)
        m[2].metric("Cache hits", usage.cache_hits)
        m[3].metric("Sources", len(bundle.sources))
        m[4].metric("Claims", len(bundle.claims))
        m[5].metric("API attempts", usage.llm_attempts, help=f"{usage.llm_calls} logical calls; includes retries")
        m[6].metric("Duration", f"{usage.elapsed_seconds}s")
        st.caption(f"Observed tokens: {usage.llm_tokens:,} · Unreported token allowance charged: "
                   f"{usage.llm_unreported_tokens:,} · In-flight allowance: {usage.llm_reserved_tokens:,}")
        if usage.cost_estimate_complete:
            st.caption(f"Estimated model cost: ${usage.estimated_cost_usd:.6f} (configured rates; not an invoice).")
        elif usage.llm_attempts:
            st.caption("Model cost is unavailable or partial: configure input/output prices and review provider billing.")
        st.markdown(f"**Stopping decision:** {bundle.stop_reason or '—'}")
        if usage.exhausted:
            st.warning("Limits reached: " + ", ".join(usage.exhausted), icon="⏱️")
for note in bundle.provider_notes:
    st.caption(f"ℹ️ {note}")

with st.expander("Full event log"):
    st.dataframe(pd.DataFrame([{"Time": e.timestamp.strftime("%H:%M:%S"), "Agent": AGENT_TITLES.get(e.agent, e.agent),
                                "Event": e.status, "Round": e.iteration, "Message": e.message} for e in bundle.events]),
                 hide_index=True, width="stretch", height=420)
with st.expander("Search activity"):
    if bundle.search_log:
        st.dataframe(pd.DataFrame([{"Round": r["iteration"], "Subquestion": r.get("subquestion_id") or "—",
                                    "Provider": r["provider"], "Query": r["query"], "Status": r["status"],
                                    "Results": r["results"], "New sources": r["new_sources"], "Note": r.get("message", "")}
                                   for r in bundle.search_log]), hide_index=True, width="stretch")
    else:
        st.caption("No searches were recorded.")
for warning in dict.fromkeys(bundle.warnings):
    st.warning(warning)
for error in bundle.errors:
    st.error(error)

a, b = st.columns([3, 1])
if a.button("New research", icon=":material/add:", key="log_new"):
    new_research()
if b.button("View results →", type="primary", width="stretch", key="log_results"):
    open_run(bundle.summary.id)
