"""Deep Researcher AI: Streamlit entry point.

Run:  streamlit run app.py
"""
import logging

import streamlit as st

from src.config import APP_NAME
from src.ui.components import hero, inject_css
from src.ui.state import current_user, get_repo, sidebar

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title=APP_NAME, page_icon=":material/science:", layout="wide")

AGENTS = [
    ("01", "Research Planner", "Decomposes the question into prioritised subquestions, queries and completion criteria."),
    ("02", "Contextual Retriever", "Searches web, academic and uploaded sources; deduplicates; follows cited leads."),
    ("03", "Source Evaluation", "Relevance, primary vs secondary, freshness, bias, syndication and injection flags."),
    ("04", "Critical Analysis", "Claims linked to exact passages, evidence matrix, contradictions and weaknesses."),
    ("05", "Gap & Follow-up", "Finds gaps, writes targeted follow-up queries, decides whether to continue."),
    ("06", "Insight Generation", "Findings, trends and hypotheses, each labelled observed, inferred or speculative."),
    ("07", "Report Builder", "Structured report with inline citations, limitations and validated references."),
    ("08", "Research Q&A", "Answers follow-up questions from the underlying evidence, with citations."),
]


def home() -> None:
    hero("Research that shows its evidence", "Multi-hop, multi-source investigations by a team of specialised AI "
                                             "agents, with every conclusion traceable to the passage that supports it.")
    user = current_user()
    if user.is_guest:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown("**Sign in for live research and a private history.** Your investigations, documents and "
                          "activity are visible only to you. Without signing in you can try the synthetic demo.")
            right.button("Sign in with Google", icon=":material/login:", on_click=st.login, args=("google",),
                         type="primary", width="stretch")
    elif user.auth_enabled:
        st.caption(f"Signed in as {user.email or user.name}. Your history is private to your account.")
    c1, c2, c3 = st.columns(3)
    c1.page_link("pages/1_Research_Workspace.py", label="Start an investigation", icon=":material/arrow_forward:")
    c2.page_link("pages/7_Research_History.py", label="Open a previous report", icon=":material/history:")
    c3.page_link("pages/8_Settings.py", label="Configure providers & limits", icon=":material/tune:")

    st.subheader("How an investigation works")
    st.markdown(
        "1. **Plan**: the question is split into subquestions covering different perspectives, including evidence "
        "*against* the premise.\n"
        "2. **Retrieve**: each subquestion is searched in the configured sources, and passages keep their provenance.\n"
        "3. **Evaluate & analyse**: sources are assessed, claims extracted, compared across *independent* sources, and "
        "contradictions recorded.\n"
        "4. **Follow up (bounded)**: gaps trigger targeted searches until the evidence is sufficient or the budget runs "
        "out.\n"
        "5. **Synthesise**: insights are labelled *observed / inferred / speculative*, then compiled into a cited report.")
    with st.expander("Workflow graph (LangGraph)"):
        st.graphviz_chart(WORKFLOW_DOT)

    st.subheader("The agent team")
    cols = st.columns(2)
    for i, (icon, name, text) in enumerate(AGENTS):
        with cols[i % 2].container(border=True):
            st.markdown(f'<div class="dr-step">{icon}</div>', unsafe_allow_html=True)
            st.markdown(f"**{name}**")
            st.caption(text)
    st.info("**Demo mode** works offline with a bundled synthetic corpus, and every demo source is labelled as "
            "fictional. **Live mode** searches OpenAlex, Crossref and arXiv (no key needed), Tavily web search (with "
            "`TAVILY_API_KEY`) and your uploads, and uses an LLM via OpenRouter when `OPENROUTER_API_KEY` is set.",
            icon=":material/info:")


WORKFLOW_DOT = """
digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="filled", fillcolor="#ffffff", color="#2f45e8",
  fontname="JetBrains Mono", fontsize=10, penwidth=1]; edge [color="#8a8a8a", fontname="JetBrains Mono", fontsize=9, arrowsize=.6];
  START [shape=square, fillcolor="#2f45e8", fontcolor="#ffffff", label="start"]; END [shape=square, fillcolor="#0f0f0f", fontcolor="#ffffff", label="end"];
  START -> planner -> retriever -> source_evaluator -> critical_analyst -> gap_analyst;
  gap_analyst -> follow_up_retrieval [label="follow_up\\n(bounded)", style=dashed];
  follow_up_retrieval -> source_evaluator;
  gap_analyst -> insight_generator [label="synthesize", style=dashed];
  insight_generator -> report_builder -> END; }
"""

inject_css()
get_repo()
sidebar()
navigation = st.navigation({
    "": [st.Page(home, title="Home", icon=":material/home:", default=True)],
    "Research": [
        st.Page("pages/1_Research_Workspace.py", title="Research Workspace", icon=":material/travel_explore:"),
        st.Page("pages/2_Research_Progress.py", title="Research Progress", icon=":material/timeline:"),
        st.Page("pages/3_Evidence_Explorer.py", title="Evidence Explorer", icon=":material/library_books:"),
        st.Page("pages/4_Critical_Analysis.py", title="Critical Analysis", icon=":material/balance:"),
        st.Page("pages/5_Insights.py", title="Insights & Hypotheses", icon=":material/lightbulb:"),
        st.Page("pages/6_Research_Report.py", title="Research Report", icon=":material/description:"),
    ],
    "Manage": [
        st.Page("pages/7_Research_History.py", title="Research History", icon=":material/history:"),
        st.Page("pages/8_Settings.py", title="Settings", icon=":material/settings:"),
    ],
})
navigation.run()
