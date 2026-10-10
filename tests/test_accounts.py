"""User accounts, password hashing, profiles and per-user run ownership."""
from __future__ import annotations

import sqlite3

import pytest

from src.auth.accounts import authenticate, register, sign_in_external
from src.auth.passwords import hash_password, verify_password
from src.database.repository import Repository
from src.models.user import UserProfile
from src.services.research_service import run_research
from tests.conftest import TODAY


def test_password_hash_is_salted_and_verifies():
    a, b = hash_password("correct horse"), hash_password("correct horse")
    assert a != b and a.startswith("scrypt$") and "correct horse" not in a
    assert verify_password("correct horse", a)
    assert not verify_password("wrong horse", a)
    assert not verify_password("anything", None) and not verify_password("anything", "garbage")


def test_register_and_authenticate(repo):
    user = register(repo, "Ada Lovelace", " Ada@Example.com ", "analytical-engine")
    assert user.email == "ada@example.com" and user.auth_provider == "password" and user.initials == "AL"
    assert authenticate(repo, "ADA@example.com", "analytical-engine").id == user.id
    assert authenticate(repo, "ada@example.com", "wrong-password") is None
    assert authenticate(repo, "nobody@example.com", "analytical-engine") is None


@pytest.mark.parametrize("name, email, password, message", [
    ("", "a@example.com", "longenough", "name"),
    ("A", "not-an-email", "longenough", "email"),
    ("A", "a@example.com", "short", "8 characters"),
])
def test_register_rejects_invalid_input(repo, name, email, password, message):
    with pytest.raises(ValueError, match=message):
        register(repo, name, email, password)


def test_duplicate_email_is_rejected(repo):
    register(repo, "Ada", "ada@example.com", "analytical-engine")
    with pytest.raises(ValueError, match="already exists"):
        register(repo, "Ada again", "ADA@example.com", "another-password")


def test_external_sign_in_creates_then_reuses_account(repo):
    first = sign_in_external(repo, "grace@example.com", "Grace Hopper", "google")
    again = sign_in_external(repo, "Grace@Example.com", "Grace H.", "google")
    assert first.id == again.id and first.auth_provider == "google"
    assert authenticate(repo, "grace@example.com", "") is None  # SSO accounts have no password


def test_profile_round_trip_and_validation(repo):
    user = register(repo, "Ada", "ada@example.com", "analytical-engine")
    profile = UserProfile(age=36, sex="Female", education="Doctorate", occupation="  Mathematician ",
                          interests=["Economics", "economics ", "Economics", ""])
    saved = repo.update_user(user.id, "Ada L.", profile)
    assert saved.name == "Ada L." and saved.profile.age == 36 and saved.profile.occupation == "Mathematician"
    assert saved.profile.interests == ["Economics", "economics"]
    assert UserProfile(sex="Unknown option", education="Nope").sex is None
    with pytest.raises(ValueError):
        UserProfile(age=5)


def test_runs_are_linked_to_their_owner(repo, settings, demo_request):
    ada = register(repo, "Ada", "ada@example.com", "analytical-engine")
    grace = register(repo, "Grace", "grace@example.com", "compiler-first")
    state = run_research(demo_request, settings, repo=repo, today=TODAY, user_id=ada.id)
    assert [r.id for r in repo.list_runs(user_id=ada.id)] == [state["run_id"]]
    assert repo.list_runs(user_id=grace.id) == []
    assert repo.load_run(state["run_id"]).summary.user_id == ada.id
    assert repo.list_runs(user_id=ada.id, mode="demo") and not repo.list_runs(user_id=ada.id, mode="live")
    repo.delete_run(state["run_id"], user_id=grace.id)  # not Grace's run: nothing happens
    assert repo.load_run(state["run_id"]) is not None
    repo.delete_run(state["run_id"], user_id=ada.id)
    assert repo.load_run(state["run_id"]) is None


def test_first_account_adopts_runs_made_before_accounts(repo, settings, demo_request):
    legacy = run_research(demo_request, settings, repo=repo, today=TODAY)  # no user: created before accounts existed
    first = register(repo, "Ada", "ada@example.com", "analytical-engine")
    second = register(repo, "Grace", "grace@example.com", "compiler-first")
    assert [r.id for r in repo.list_runs(user_id=first.id)] == [legacy["run_id"]]
    assert repo.list_runs(user_id=second.id) == []


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # the runs table as it was before accounts
        conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, question TEXT NOT NULL, status TEXT NOT NULL, "
                     "mode TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, parent_run_id TEXT, "
                     "request TEXT NOT NULL, plan TEXT, usage TEXT, statuses TEXT, stop_reason TEXT, summary TEXT, "
                     "warnings TEXT NOT NULL DEFAULT '[]', errors TEXT NOT NULL DEFAULT '[]', "
                     "provider_notes TEXT NOT NULL DEFAULT '[]', counts TEXT NOT NULL DEFAULT '{}')")
    repo = Repository(path)
    Repository(path)  # migration is idempotent
    with sqlite3.connect(path) as conn:
        assert "user_id" in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert repo.count_users() == 0
