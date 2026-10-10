"""Page 7: Research History. The signed-in user's own runs and activity (private per user)."""
import pandas as pd
import streamlit as st

from src.ui.components import page_header
from src.ui.state import current_user, get_repo, select_run, selected_run_id

repo, user = get_repo(), current_user()
page_header("Library", "Research History",
            "Your investigations and activity. They are private to your account and can be reopened without "
            "repeating the research." if user.auth_enabled else
            "Completed investigations are stored and can be reopened without repeating the research.")
if user.is_guest:
    st.info("You're browsing as a guest: demo runs from this session are listed below and are removed after 24 hours. "
            "Sign in to keep a private, permanent history.", icon=":material/info:")

tab_runs, tab_activity = st.tabs(["My research", "My activity"])

with tab_runs:
    runs = repo.list_runs(user.id, limit=200)
    if not runs:
        st.info("No research runs yet.", icon=":material/info:")
        st.page_link("pages/1_Research_Workspace.py", label="Start an investigation", icon=":material/arrow_forward:")
    else:
        status_filter = st.segmented_control("Status", ["all", "completed", "failed", "running"], default="all") or "all"
        search = st.text_input("Search questions")
        runs = [r for r in runs if (status_filter == "all" or r.status == status_filter)
                and (not search or search.lower() in r.question.lower())]
        st.dataframe(pd.DataFrame([{
            "Question": r.question, "Created": r.created_at.strftime("%d %b %Y %H:%M"), "Status": r.status,
            "Mode": "demo (synthetic)" if r.mode == "demo" else "live", "Sources": r.counts.get("sources", 0),
            "Claims": r.counts.get("claims", 0), "Data points": r.counts.get("data_points", 0),
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
                        if repo.delete_run(run.id, user.id):
                            repo.log_activity(user.id, "run_deleted", run.id, {"question": run.question[:200]})
                        if current == run.id:
                            st.session_state.pop("selected_run_id", None)
                        st.session_state.pop("_bundle_cache", None)
                        st.rerun()

LABELS = {"login": "Signed in", "run_started": "Started research", "run_completed": "Research completed",
          "run_failed": "Research failed", "run_deleted": "Deleted a run", "qa": "Asked a follow-up question",
          "export": "Exported a report", "upload": "Uploaded a document", "data_deleted": "Deleted all data"}

with tab_activity:
    activity = repo.list_activity(user.id)
    if not activity:
        st.caption("No activity recorded yet.")
    else:
        st.dataframe(pd.DataFrame([{
            "When": a["created_at"].replace("T", " ")[:16], "Activity": LABELS.get(a["kind"], a["kind"]),
            "Details": "; ".join(f"{k}: {v}" for k, v in a["detail"].items()), "Run": a["run_id"] or ""}
            for a in activity]), hide_index=True, width="stretch")

if not user.is_guest:
    st.divider()
    with st.expander("Delete my data", icon=":material/delete_forever:"):
        st.write("Permanently delete **all** of your research runs (with their evidence and reports), uploaded "
                 "documents, activity history and preferences. This cannot be undone.")
        confirm = st.text_input("Type DELETE to confirm", key="confirm_delete_all")
        if st.button("Delete everything", type="primary", disabled=confirm != "DELETE"):
            count = repo.delete_user_data(user.id)
            repo.log_activity(user.id, "data_deleted", detail={"runs": count})
            for key in ("selected_run_id", "_bundle_cache"):
                st.session_state.pop(key, None)
            st.success(f"Deleted {count} run(s) and all associated data.")
            st.rerun()
