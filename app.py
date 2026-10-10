"""Deep Researcher AI: Streamlit entry point.

Run:  streamlit run app.py
"""
import logging

import streamlit as st

from src.config import APP_NAME
from src.ui.components import hero, inject_css
from src.ui.state import get_repo, sidebar

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title=APP_NAME, page_icon="🔬", layout="wide")

AGENTS = [
    ("🧭", "Research Planner", "Decomposes the question into prioritised subquestions, queries and completion criteria."),
    ("🔎", "Contextual Retriever", "Searches web, academic and uploaded sources; deduplicates; follows cited leads."),
    ("⚖️", "Source Evaluation", "Relevance, primary vs secondary, freshness, bias, syndication and injection flags."),
    ("🧪", "Critical Analysis", "Claims linked to exact passages, evidence matrix, contradictions and weaknesses."),
    ("🕳️", "Gap & Follow-up", "Finds gaps, writes targeted follow-up queries, decides whether to continue."),
    ("💡", "Insight Generation", "Findings, trends and hypotheses, each labelled observed, inferred or speculative."),
    ("📝", "Report Builder", "Structured report with inline citations, limitations and validated references."),
    ("💬", "Research Q&A", "Answers follow-up questions from the underlying evidence, with citations."),
]


def home() -> None:
    hero(f"🔬 {APP_NAME}", "Multi-hop, multi-source investigations by a team of specialised AI agents, with every "
                           "conclusion traceable to its evidence.")
    c1, c2, c3 = st.columns(3)
    c1.page_link("pages/1_Research_Workspace.py", label="Start an investigation", icon="🚀")
    c2.page_link("pages/7_Research_History.py", label="Open a previous report", icon="🗂️")
    c3.page_link("pages/8_Settings.py", label="Configure providers & limits", icon="⚙️")

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
            st.markdown(f"{icon} **{name}**")
            st.caption(text)
    st.info("**Demo mode** works offline with a bundled synthetic corpus, and every demo source is labelled as "
            "fictional. **Live mode** searches OpenAlex, Crossref and arXiv (no key needed), Tavily web search (with "
            "`TAVILY_API_KEY`) and your uploads, and uses an LLM via OpenRouter when `OPENROUTER_API_KEY` is set.",
            icon="ℹ️")


WORKFLOW_DOT = """
digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2ff", color="#6366f1", fontname="Helvetica"];
  START [shape=circle, fillcolor="#e5e7eb", label="start"]; END [shape=doublecircle, fillcolor="#e5e7eb", label="end"];
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
    "": [st.Page(home, title="Home", icon="🏠", default=True)],
    "Research": [
        st.Page("pages/1_Research_Workspace.py", title="Research Workspace", icon="🚀"),
        st.Page("pages/2_Research_Progress.py", title="Research Progress", icon="📡"),
        st.Page("pages/3_Evidence_Explorer.py", title="Evidence Explorer", icon="📚"),
        st.Page("pages/4_Critical_Analysis.py", title="Critical Analysis", icon="⚖️"),
        st.Page("pages/5_Insights.py", title="Insights & Hypotheses", icon="💡"),
        st.Page("pages/6_Research_Report.py", title="Research Report", icon="📝"),
    ],
    "Manage": [
        st.Page("pages/7_Research_History.py", title="Research History", icon="🗂️"),
        st.Page("pages/8_Settings.py", title="Settings", icon="⚙️"),
    ],
})
navigation.run()
