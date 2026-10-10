"""Deep Researcher AI: Streamlit entry point.

Run:  streamlit run app.py
"""
import logging

import streamlit as st

from src.config import APP_NAME
from src.models.research import DEMO_QUESTIONS
from src.ui.components import AGENT_INFO, AGENT_TITLES, eyebrow, html, inject_css
from src.ui.state import current_user, get_repo, new_research, sidebar, login_google

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title=APP_NAME, page_icon="assets/icon.svg", layout="wide")


def try_demo() -> None:
    """Open the workspace in demo mode with the first sample question selected."""
    for key in [k for k in st.session_state if k.startswith("q_")]:
        st.session_state.pop(key, None)
    st.session_state.update({"q_mode": "demo", "q_demo": DEMO_QUESTIONS[0]})


def home() -> None:
    user = current_user()
    left, right = st.columns([1.05, 0.95], gap="large", vertical_alignment="center")
    with left:
        html(eyebrow("AI-powered deep research")
             + '<div class="ds-hero-title">From complex questions<br>to <em>clear understanding.</em></div>'
               '<p class="ds-lead">A team of specialised AI agents investigates, verifies and synthesises research '
               "you can trust, with every finding traceable to the passage that supports it.</p>")
        b1, b2 = st.columns(2)
        if b1.button("Try Demo →", type="primary", width="stretch", key="hero_demo", on_click=try_demo):
            st.switch_page("app_pages/1_Research_Workspace.py")
        if user.is_guest:
            b2.button("Sign in with Google", icon=":material/login:", width="stretch", key="hero_signin",
                      on_click=login_google)
        elif b2.button("Start researching", icon=":material/travel_explore:", width="stretch", key="hero_start"):
            new_research()
        html('<div class="ds-proof"><div class="ds-avatars"><span>R</span><span>A</span><span>T</span><span>+</span>'
             '</div><span><b>Built for curious minds</b><small>Researchers · Analysts · Teams</small></span></div>')
        if user.is_guest:
            st.caption("Without signing in you can explore the demo with three sample questions. Sign in to research "
                       "any question with live sources and keep a private history.")
        elif user.auth_enabled:
            st.caption(f"Signed in as {user.email or user.name}. Your history is private to your account.")
    with right:
        rows = [("planner", "Complete"), ("retriever", "Searching"), ("critical_analyst", "Queued")]
        agent_rows = "".join(f'<div class="ds-vrow"><span class="ds-icon {AGENT_INFO[a][1]}">{AGENT_INFO[a][0]}</span>'
                             f'<span>{AGENT_TITLES[a]}</span><b>{state}</b></div>' for a, state in rows)
        html('<div class="ds-visual"><div class="ds-orb one"></div><div class="ds-orb two"></div><div class="ds-vcard">'
             '<div class="ds-vtop"><span class="ds-dot"></span> RESEARCH IN PROGRESS <span class="ds-vlive">LIVE</span>'
             f'</div><h3>{DEMO_QUESTIONS[0]}</h3>{agent_rows}<div class="ds-vfoot"><span>17 sources analysed</span>'
             '<span>•••</span></div></div><div class="ds-chip a">✦ &nbsp; Verified citations</div>'
             '<div class="ds-chip b">⌁ &nbsp; 8 agents working</div></div>')
    html('<div class="ds-foot"><span>POWERED BY A TEAM OF SPECIALISED AI AGENTS</span><div><span>◈ Research</span>'
         '<span>◎ Evidence</span><span>✳ Synthesis</span></div></div>')

    st.write("")
    html('<div style="text-align:center">' + eyebrow("A better way to research", center=True)
         + '<div class="ds-title">Depth without the busywork.</div></div>')
    features = [("⌕", "Investigate deeply", "Searches web, news, academic papers (OpenAlex, Crossref, arXiv) and your "
                 "own documents, then follows up on gaps."),
                ("✓", "Verify every claim", "Each finding links to the exact passage it came from; citations are "
                 "checked and contradictions are surfaced."),
                ("✧", "Make sense of it all", "A clear report with analysis, labelled insights (observed, inferred, "
                 "speculative) and open questions.")]
    for col, (icon, title, text) in zip(st.columns(3), features):
        col.markdown(f'<div class="ds-feature"><span class="ds-icon ds-purple">{icon}</span><h3>{title}</h3>'
                     f"<p>{text}</p></div>", unsafe_allow_html=True)

    st.write("")
    st.subheader("How an investigation works")
    with st.container(key="card-how"):
        st.markdown(
            "1. **Plan**: the question is split into subquestions covering different perspectives, including evidence "
            "*against* the premise.\n"
            "2. **Retrieve**: each subquestion is searched in the configured sources, and passages keep their "
            "provenance.\n"
            "3. **Evaluate & analyse**: sources are assessed, claims extracted, compared across *independent* sources, "
            "and contradictions recorded.\n"
            "4. **Follow up (bounded)**: gaps trigger targeted searches until the evidence is sufficient or the budget "
            "runs out.\n"
            "5. **Synthesise**: insights are labelled *observed / inferred / speculative*, then compiled into a cited "
            "report.")
        with st.expander("Workflow graph (LangGraph)"):
            st.graphviz_chart(WORKFLOW_DOT)
    st.info("**Demo mode** works offline with a bundled synthetic dataset about AI and enterprise software, limited to "
            "three sample questions; every demo source is labelled as fictional. **Live mode** (signed in) searches "
            "OpenAlex, Crossref, arXiv, Tavily web search and your uploads, and uses an LLM via OpenRouter.",
            icon=":material/info:")


WORKFLOW_DOT = """
digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fillcolor="#ffffff", color="#9d89e2",
  fontname="Helvetica", fontsize=10, penwidth=1]; edge [color="#9294a6", fontname="Helvetica", fontsize=9, arrowsize=.6];
  START [shape=circle, fillcolor="#7159dc", fontcolor="#ffffff", label="start"]; END [shape=circle, fillcolor="#111329", fontcolor="#ffffff", label="end"];
  START -> planner -> retriever -> source_evaluator -> critical_analyst -> gap_analyst;
  gap_analyst -> follow_up_retrieval [label="follow_up\\n(bounded)", style=dashed];
  follow_up_retrieval -> source_evaluator;
  gap_analyst -> insight_generator [label="synthesize", style=dashed];
  insight_generator -> data_visualizer -> report_builder -> END; }
"""

inject_css()
get_repo()
navigation = st.navigation({
    "": [st.Page(home, title="Welcome", icon=":material/home:", default=True)],
    "Workspace": [
        st.Page("app_pages/1_Research_Workspace.py", title="Research workspace", icon=":material/travel_explore:"),
        st.Page("app_pages/2_Research_Progress.py", title="Agents in action", icon=":material/motion_photos_on:"),
        st.Page("app_pages/3_Research_Results.py", title="Research results", icon=":material/article:"),
        st.Page("app_pages/7_Research_History.py", title="Research library", icon=":material/collections_bookmark:"),
    ],
    "Account": [st.Page("app_pages/8_Settings.py", title="Settings", icon=":material/settings:")],
})
sidebar()
navigation.run()
