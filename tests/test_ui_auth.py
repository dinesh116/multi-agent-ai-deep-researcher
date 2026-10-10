"""UI identity modes: local single user (no [auth]) and guest (sign-in configured, not signed in)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
AUTH_SECRETS = {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "test-cookie-secret",
                "client_id": "test-client", "client_secret": "test-secret",
                "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    import streamlit as st
    st.cache_resource.clear()
    yield
    get_settings.cache_clear()
    st.cache_resource.clear()


def app(with_auth: bool) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    if with_auth:
        at.secrets["auth"] = AUTH_SECRETS
    return at.run()


def test_local_mode_is_single_admin_user():
    at = app(with_auth=False)
    assert not at.exception
    assert not [b for b in at.button if "Sign in" in b.label]  # no login without [auth]
    at.switch_page("pages/8_Settings.py").run()
    assert not at.exception and any("App-wide settings" in s.value for s in at.subheader)  # local user is admin


def test_guest_gets_sign_in_and_demo_only():
    at = app(with_auth=True)
    assert not at.exception
    assert [b for b in at.button if "Sign in with Google" in b.label]
    at.switch_page("pages/1_Research_Workspace.py").run()
    mode = [r for r in at.radio if r.label == "Mode"][0]
    assert mode.value == "demo" and mode.disabled  # live research needs sign-in
    assert any("Sign in (sidebar) to run live research" in c.value for c in at.caption)
    at.switch_page("pages/8_Settings.py").run()
    assert any("Sign in to save personal preferences" in i.value for i in at.info)
    assert not any("App-wide settings" in s.value for s in at.subheader)  # guests never see admin settings


def test_guest_demo_run_is_listed_only_for_that_guest():
    at = app(with_auth=True)
    at.switch_page("pages/1_Research_Workspace.py").run()
    at.text_area(key="q_text").set_value("How will agentic AI transform enterprise software over the next five years?").run()
    [b for b in at.button if "Run research" in b.label][0].click().run()
    assert not at.exception and at.success
    at.switch_page("pages/7_Research_History.py").run()
    assert not at.exception and any("guest" in i.value.lower() for i in at.info)
    assert at.dataframe  # this guest sees their own demo run
    other = app(with_auth=True)  # a different browser session = a different guest
    other.switch_page("pages/7_Research_History.py").run()
    assert any("No research runs yet" in i.value for i in other.info)
