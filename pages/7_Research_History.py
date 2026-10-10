"""Page 7: My research runs. Reopen or delete the signed-in user's investigations."""
import pandas as pd
import streamlit as st

from src.ui.components import page_header
from src.ui.state import get_repo, require_user, select_run, selected_run_id

user = require_user()
repo = get_repo()
page_header("Library", "My research runs", "Your investigations, live and demo. Reopen any of them without repeating the research.")

runs = repo.list_runs(limit=200, user_id=user.id)
if not runs:
    st.info("No research runs yet.", icon=":material/info:")
    st.page_link("pages/1_Research_Workspace.py", label="Start an investigation", icon=":material/arrow_forward:")
    st.page_link("pages/9_Demo.py", label="Or try the offline demo", icon=":material/science:")
    st.stop()

status_filter = st.segmented_control("Status", ["all", "completed", "failed", "running"], default="all") or "all"
search = st.text_input("Search questions")
runs = [r for r in runs if (status_filter == "all" or r.status == status_filter)
        and (not search or search.lower() in r.question.lower())]
st.dataframe(pd.DataFrame([{
    "Question": r.question, "Created": r.created_at.strftime("%d %b %Y %H:%M"), "Status": r.status,
    "Mode": "demo (synthetic)" if r.mode == "demo" else "live", "Sources": r.counts.get("sources", 0),
    "Claims": r.counts.get("claims", 0), "Contradictions": r.counts.get("contradictions", 0),
    "Rounds": r.counts.get("iterations", 0), "Refines": r.parent_run_id or ""} for r in runs]),
    hide_index=True, width="stretch")

current = selected_run_id()
for run in runs:
    with st.container(border=True):
        top, buttons = st.columns([5, 1.6])
        marker = "● " if run.id == current else ""
        top.markdown(f"{marker}**{run.question}**")
        top.caption(f"{run.created_at:%d %b %Y %H:%M} · {run.status} · {'demo' if run.mode == 'demo' else 'live'} · "
                    f"{run.counts.get('sources', 0)} sources · {run.counts.get('insights', 0)} insights")
        if run.summary:
            with top.expander("Summary of findings"):
                st.markdown(run.summary)
        b1, b2 = buttons.columns(2)
        if b1.button("Open", key=f"open_{run.id}", disabled=run.status == "running"):
            select_run(run.id)
            st.switch_page("pages/6_Research_Report.py")
        with b2.popover("Delete", icon=":material/delete:"):
            st.write("Delete this run and all of its stored sources, evidence, report and Q&A?")
            if st.button("Delete", key=f"del_{run.id}", type="primary"):
                repo.delete_run(run.id, user_id=user.id)
                if current == run.id:
                    st.session_state.pop("selected_run_id", None)
                st.session_state.pop("_bundle_cache", None)
                st.rerun()
