"""Sign-in / create-account screen: Google, Microsoft, or email and password."""
from __future__ import annotations

import streamlit as st

from src.auth.accounts import authenticate, register
from src.auth.session import SSO_PROVIDERS, configured_providers, start_session
from src.ui.brand import logo_data_uri
from src.ui.state import get_repo
from src.ui.theme import hide_sidebar

SIGN_IN, CREATE = "Sign in", "Create account"


def login_page() -> None:
    hide_sidebar()
    repo = get_repo()
    st.markdown('<div style="height: 4vh"></div>', unsafe_allow_html=True)
    brand, card = st.columns([1.1, 0.9], gap="large", vertical_alignment="center")

    with brand:
        image = logo_data_uri("hero")
        if image:
            st.markdown(f'<div class="dr-login-figure"><img src="{image}" alt="Deep Research Agent: a robot scientist in '
                        f'a lab coat holding a magnifying glass"></div>', unsafe_allow_html=True)
        st.markdown('<div class="dr-login-copy"><div class="dr-kicker" style="margin-top:1.4rem">Deep Researcher AI</div>'
                    '<h1>Research that shows its evidence.</h1><p>A team of AI agents plans, searches, weighs and cites, '
                    'so every conclusion traces back to the passage that supports it.</p></div>', unsafe_allow_html=True)

    with card, st.container(key="glass_auth"):
        mode = st.segmented_control("Account", [SIGN_IN, CREATE], default=SIGN_IN, key="auth_mode",
                                    label_visibility="collapsed") or SIGN_IN
        title, subtitle = (("Welcome back", "Sign in to continue your research.") if mode == SIGN_IN else
                           ("Create your account", "Your runs and profile stay private to you."))
        st.markdown(f'<p class="dr-auth-title">{title}</p><p class="dr-auth-sub">{subtitle}</p>', unsafe_allow_html=True)

        available = configured_providers()
        for name, label in SSO_PROVIDERS.items():
            if st.button(f"Continue with {label}", key=f"sso_{name}", width="stretch", disabled=name not in available,
                         help=None if name in available else f"{label} sign-in is not configured on this server yet."):
                st.login(name)
        if not available:
            st.caption("Google and Microsoft sign-in become available once OAuth keys are added to "
                       "`.streamlit/secrets.toml` (see `secrets.toml.example`).")

        st.markdown('<div class="dr-or">OR WITH EMAIL</div>', unsafe_allow_html=True)
        if mode == SIGN_IN:
            with st.form("sign_in", border=False):
                email = st.text_input("Email", placeholder="you@example.com", autocomplete="email")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                if st.form_submit_button("Sign in", type="primary"):
                    user = authenticate(repo, email, password)
                    if user:
                        start_session(user)
                        st.rerun()
                    st.error("That email and password don't match an account.")
        else:
            with st.form("create_account", border=False):
                name = st.text_input("Full name", placeholder="Your name", autocomplete="name")
                email = st.text_input("Email", placeholder="you@example.com", autocomplete="email")
                password = st.text_input("Password", type="password", autocomplete="new-password",
                                         help="At least 8 characters.")
                if st.form_submit_button("Create account", type="primary"):
                    try:
                        user = register(repo, name, email, password)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        start_session(user)
                        st.session_state["welcome"] = True
                        st.rerun()
        st.markdown('<p class="dr-fineprint">Runs, reports and your profile are linked to your account and stored '
                    'privately.</p>', unsafe_allow_html=True)
