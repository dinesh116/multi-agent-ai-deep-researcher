"""Demo: run the full multi-agent workflow offline on the bundled SYNTHETIC corpus, on its own page."""
import streamlit as st
from pydantic import ValidationError

from src.models.research import DEPTH_PRESETS, Depth, ResearchMode, ResearchRequest
from src.ui.components import demo_banner, page_header
from src.ui.runner import run_with_progress
from src.ui.state import get_repo, require_user, select_run

user = require_user()
repo = get_repo()
page_header("Library", "Demo", "See the whole investigation workflow in action, offline. No API keys are needed and "
                               "nothing is sent over the network.")
demo_banner("demo")

DEMO_QUESTIONS = [
    "How will agentic AI transform enterprise software over the next five years?",
    "What evidence supports or contradicts the claim that AI agents will replace traditional SaaS workflows?",
    "What are the latest research developments in retrieval-augmented generation?",
    "How are major payment companies adopting generative AI?",
]

with st.container(key="glass_demo"):
    st.markdown("The demo corpus has 27 fictional sources. It deliberately includes contradictions, a press release "
                "reprinted by a news site, an outdated forecast, opinion pieces and a prompt-injection attempt, so every "
                "agent has something to find.")
    picked = st.pills("Pick a question", DEMO_QUESTIONS, default=DEMO_QUESTIONS[0], key="demo_pick")
    with st.form("demo_run", border=False):
        question = st.text_area("Demo question", value=picked or DEMO_QUESTIONS[0], height=80, max_chars=600)
        c1, c2 = st.columns(2)
        depth = c1.segmented_control("Depth", [d.value for d in Depth], default=Depth.STANDARD.value,
                                     format_func=str.title) or Depth.STANDARD.value
        rounds = c2.slider("Maximum follow-up rounds", 1, 6, 2)
        preset = DEPTH_PRESETS[Depth(depth)]
        st.caption(f"{preset['subquestions']} subquestions · up to {preset['budget'].max_searches} searches · "
                   f"{preset['budget'].max_sources} sources")
        launch = st.form_submit_button("Run demo", type="primary", icon=":material/play_arrow:")

if launch:
    try:
        request = ResearchRequest(question=question, mode=ResearchMode.DEMO, depth=Depth(depth), max_iterations=rounds,
                                  use_llm=False)
    except ValidationError as exc:
        for error in exc.errors():
            st.error(error["msg"].removeprefix("Value error, "))
        st.stop()
    st.markdown(f"**Investigating (demo):** {request.question}")
    run_with_progress(request)
    st.stop()

demo_runs = repo.list_runs(limit=5, user_id=user.id, mode="demo")
if demo_runs:
    st.subheader("Your demo runs")
    for run in demo_runs:
        left, right = st.columns([5, 1], vertical_alignment="center")
        left.markdown(f"**{run.question}**")
        left.caption(f"{run.created_at:%d %b %Y %H:%M} · {run.status} · {run.counts.get('sources', 0)} synthetic sources")
        if right.button("Open", key=f"demo_open_{run.id}", disabled=run.status == "running", width="stretch"):
            select_run(run.id)
            st.switch_page("pages/6_Research_Report.py")
