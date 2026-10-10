"""Deep Researcher AI: Streamlit entry point.

Run:  streamlit run app.py

Visitors see only the sign-in screen. Once signed in, the sidebar menu gives access to research, the user's own
run history, the offline demo and their profile.
"""
import logging

import streamlit as st

from src.auth.session import current_user
from src.config import APP_NAME
from src.ui.brand import brand_logo
from src.ui.components import inject_css
from src.ui.login import login_page
from src.ui.state import get_repo, sidebar

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title=APP_NAME, page_icon=":material/science:", layout="wide")

inject_css()
user = current_user(get_repo())
if user is None:
    st.navigation([st.Page(login_page, title="Sign in", icon=":material/login:")], position="hidden").run()
    st.stop()

brand_logo()
sidebar(user)
navigation = st.navigation({
    "": [
        st.Page("pages/0_Home.py", title="Home", icon=":material/home:", default=True),
        st.Page("pages/1_Research_Workspace.py", title="New research", icon=":material/add:"),
    ],
    "Research": [
        st.Page("pages/2_Research_Progress.py", title="Progress", icon=":material/timeline:"),
        st.Page("pages/3_Evidence_Explorer.py", title="Evidence explorer", icon=":material/library_books:"),
        st.Page("pages/4_Critical_Analysis.py", title="Critical analysis", icon=":material/balance:"),
        st.Page("pages/5_Insights.py", title="Insights", icon=":material/lightbulb:"),
        st.Page("pages/6_Research_Report.py", title="Report", icon=":material/description:"),
    ],
    "Library": [
        st.Page("pages/7_Research_History.py", title="My research runs", icon=":material/history:"),
        st.Page("pages/9_Demo.py", title="Demo", icon=":material/science:"),
    ],
    "Account": [
        st.Page("pages/10_Profile.py", title="Update profile", icon=":material/person:"),
        st.Page("pages/8_Settings.py", title="Settings", icon=":material/tune:"),
    ],
})
navigation.run()
