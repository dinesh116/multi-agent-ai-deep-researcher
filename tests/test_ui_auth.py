"""UI identity modes: local single user (no [auth]) and guest (sign-in configured, not signed in)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
AUTH_SECRETS = {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "test-cookie-secret",
                "google": {"client_id": "test-client", "client_secret": "test-secret",
                           "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    import streamlit as st
    from streamlit import config
    # Ignore the developer's real .streamlit/secrets.toml: each test sets exactly the secrets it needs.
    old_files = config.get_option("secrets.files")
    config.set_option("secrets.files", [str(tmp_path / "no-secrets.toml")])
    st.secrets._secrets = None
    st.cache_resource.clear()
    yield
    config.set_option("secrets.files", old_files)
    st.secrets._secrets = None
    get_settings.cache_clear()
    st.cache_resource.clear()


def app(with_auth: bool) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    if with_auth:
        at.secrets["auth"] = AUTH_SECRETS
    return at.run()


def start_demo(at: AppTest, question_index: int = 0) -> AppTest:
    from src.models.research import DEMO_QUESTIONS
    at.switch_page("app_pages/1_Research_Workspace.py").run()
    if at.segmented_control:  # users who may run live research choose Demo first; guests are always in demo
        at.segmented_control(key="q_mode").set_value("demo").run()
    at.radio(key="q_demo").set_value(DEMO_QUESTIONS[question_index]).run()
    at.button(key="start_research").click().run()
    return at


def test_local_mode_is_single_admin_user():
    at = app(with_auth=False)
    assert not at.exception
    assert not [b for b in at.button if "Sign in" in b.label]  # no login without [auth]
    at.switch_page("app_pages/8_Settings.py").run()
    assert not at.exception and any("App-wide settings" in s.value for s in at.subheader)  # local user is admin


def test_guest_gets_sign_in_and_demo_only():
    at = app(with_auth=True)
    assert not at.exception
    assert [b for b in at.button if "Sign in with Google" in b.label]
    at.switch_page("app_pages/1_Research_Workspace.py").run()
    assert not at.exception
    assert not at.segmented_control  # no Live / Demo switch for guests
    assert not [t for t in at.text_area if t.key == "q_text"]  # no free-text question in demo mode
    assert at.radio(key="q_demo").options == ["How will agentic AI transform enterprise software over the next five years?",
                                              "Which emerging technologies could create new business opportunities in India?",
                                              "What evidence supports or contradicts the claim that AI agents will replace "
                                              "traditional SaaS workflows?"]
    assert any("Sign in (sidebar) to research any question live" in c.value for c in at.caption)
    at.switch_page("app_pages/8_Settings.py").run()
    assert any("Sign in to save personal preferences" in i.value for i in at.info)
    assert not any("App-wide settings" in s.value for s in at.subheader)  # guests never see admin settings


def test_signed_in_style_user_can_switch_to_live_with_free_text():
    at = app(with_auth=False)  # local user can use live, like a signed-in user
    at.switch_page("app_pages/1_Research_Workspace.py").run()
    at.segmented_control(key="q_mode").set_value("live").run()
    assert not at.exception and [t for t in at.text_area if t.key == "q_text"]
    at.segmented_control(key="q_mode").set_value("demo").run()
    assert not [t for t in at.text_area if t.key == "q_text"] and at.radio(key="q_demo")


def test_demo_run_renders_every_screen():
    at = start_demo(app(with_auth=False), question_index=2)
    assert not at.exception and at.success  # agents in action: finished
    for page in ("app_pages/3_Research_Results.py", "app_pages/2_Research_Progress.py", "app_pages/7_Research_History.py",
                 "app_pages/8_Settings.py"):  # the Welcome page already rendered when the app started
        at.switch_page(page).run()
        assert not at.exception, page
    at.switch_page("app_pages/3_Research_Results.py").run()
    assert len(at.tabs) == 7 and at.tabs[0].label == "Overview"


def test_guest_demo_run_is_listed_only_for_that_guest():
    from src.models.research import DEMO_QUESTIONS
    at = start_demo(app(with_auth=True))
    assert not at.exception and at.success
    at.switch_page("app_pages/7_Research_History.py").run()
    assert not at.exception and any("guest" in i.value.lower() for i in at.info)
    assert any(DEMO_QUESTIONS[0] in m.value for m in at.markdown)  # this guest sees their own demo run
    other = app(with_auth=True)  # a different browser session = a different guest
    other.switch_page("app_pages/7_Research_History.py").run()
    assert any("No research runs yet" in i.value for i in other.info)
