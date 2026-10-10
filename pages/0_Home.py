"""Home: ask a question, reopen recent research, see how the workflow runs and meet the agent team."""
from datetime import datetime
from html import escape

import streamlit as st
from pydantic import ValidationError

from src.models.research import Depth, ResearchMode, ResearchRequest
from src.ui.brand import logo_data_uri
from src.ui.graphics import agent_cards_html, workflow_html
from src.ui.state import effective_settings, get_repo, preference, require_user, select_run

user = require_user()
repo, settings = get_repo(), effective_settings()

if st.session_state.pop("welcome", False):
    st.toast(f"Welcome, {user.first_name}! Your account is ready.", icon=":material/waving_hand:")

hour = datetime.now().hour
greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
top_left, top_right = st.columns([3, 1], vertical_alignment="bottom")
top_left.markdown(f'<div class="dr-greeting"><div class="dr-kicker">Home</div><h2>{greeting}, '
                  f'{escape(user.first_name)}</h2></div>', unsafe_allow_html=True)
if top_right.button("New research", icon=":material/add:", type="primary", width="stretch"):
    st.switch_page("pages/1_Research_Workspace.py")

# ---------------------------------------------------------------------- hero: ask a question
with st.container(key="glass_hero"):
    copy, figure = st.columns([1.15, 1], gap="large", vertical_alignment="center")
    with copy:
        st.markdown('<div class="dr-kicker">Multi-agent deep research</div>'
                    '<h1 class="dr-display">Research that shows its evidence.</h1>'
                    '<p class="dr-lead">Ask a hard question. Eight specialised agents plan the investigation, search web '
                    'and academic sources, weigh the evidence and return a cited report, with every conclusion traceable '
                    'to the passage behind it.</p>', unsafe_allow_html=True)
        with st.form("quick_ask", border=False):
            question = st.text_input("Research question",
                                     placeholder="How will agentic AI transform enterprise software?")
            if st.form_submit_button("Investigate", type="primary", icon=":material/arrow_forward:"):
                try:
                    request = ResearchRequest(question=question or "", mode=ResearchMode.LIVE,
                                              depth=Depth(preference("depth")),
                                              max_iterations=int(preference("max_iterations")),
                                              use_llm=settings.llm_configured)
                except ValidationError as exc:
                    for error in exc.errors():
                        st.error(error["msg"].removeprefix("Value error, "))
                else:
                    st.session_state["pending_request"] = request.model_dump_json()
                    st.switch_page("pages/2_Research_Progress.py")
        sources = ["OpenAlex", "Crossref", "arXiv"] + (["Tavily web"] if settings.web_search_configured else []) + \
                  ["Your documents"]
        st.markdown('<div class="dr-chips">' + "".join(f'<span class="dr-chip">{s}</span>' for s in sources) + "</div>",
                    unsafe_allow_html=True)
        st.page_link("pages/9_Demo.py", label="Want to look around first? Open the demo", icon=":material/science:")
    with figure:
        image = logo_data_uri("hero")
        if image:
            st.markdown(f'<div class="dr-figure"><img src="{image}" alt="Deep Research Agent: a robot scientist in a lab '
                        f'coat holding a magnifying glass"><div class="dr-tag"><span class="dr-dot-live"></span>'
                        f'DR-01 · DEEP RESEARCH AGENT</div></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------- the user's recent research
with st.container(key="glass_recent"):
    head, link = st.columns([3, 1], vertical_alignment="center")
    head.markdown('<p class="dr-section-title">Your recent research</p>', unsafe_allow_html=True)
    link.page_link("pages/7_Research_History.py", label="All my runs", icon=":material/arrow_forward:")
    runs = repo.list_runs(limit=4, user_id=user.id)
    if not runs:
        st.caption("No investigations yet. Ask a question above, or open the demo to see a finished report.")
    for run in runs:
        q, meta, action = st.columns([6, 2.2, 1], vertical_alignment="center")
        q.markdown(f'<p class="dr-run-q">{escape(run.question)}</p>', unsafe_allow_html=True)
        mode = "demo" if run.mode == "demo" else "live"
        meta.markdown(f'<div class="dr-run-meta"><span class="dr-pill {mode}">{mode}</span>'
                      f'<span class="dr-pill {escape(run.status)}">{escape(run.status)}</span></div>',
                      unsafe_allow_html=True)
        if action.button("Open", key=f"home_open_{run.id}", disabled=run.status == "running", width="stretch"):
            select_run(run.id)
            st.switch_page("pages/6_Research_Report.py")

# ---------------------------------------------------------------------- LangGraph workflow
with st.container(key="glass_workflow"):
    st.markdown('<div class="dr-kicker">LangGraph workflow</div><p class="dr-section-title" style="margin-top:.4rem">'
                'How an investigation flows</p><p class="dr-section-lead">Routing is rule-based. Follow-up rounds target '
                'the weakest evidence and stop at the iteration, search, source or time limit.</p>',
                unsafe_allow_html=True)
    st.html(workflow_html())

# ---------------------------------------------------------------------- the agent team
st.markdown('<p class="dr-section-title" style="margin-top:.6rem">Get to know your agent team</p>'
            '<p class="dr-section-lead">Eight specialists, one job each. LLM-optional agents use a language model when '
            'one is configured and fall back to transparent rules when not.</p>', unsafe_allow_html=True)
st.html(agent_cards_html())
st.caption("Citations are checked for traceability, not truth. Verify important conclusions against the original sources.")
