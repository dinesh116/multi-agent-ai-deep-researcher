"""Account registration and sign-in (framework-independent, so it can be unit tested)."""
from __future__ import annotations

from src.auth.passwords import hash_password, validate_password, verify_password
from src.models.user import User, normalize_email


def _adopt_legacy_runs(repo, user: User) -> None:
    """The first account on an existing installation inherits runs made before accounts existed."""
    if repo.count_users() == 1:
        repo.claim_unowned_runs(user.id)


def register(repo, name: str, email: str, password: str) -> User:
    """Create an email/password account. Raises ValueError with a user-facing message on invalid input."""
    email = normalize_email(email)
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Please enter your name.")
    validate_password(password)
    user = repo.create_user(email, name, "password", hash_password(password))
    _adopt_legacy_runs(repo, user)
    return user


def authenticate(repo, email: str, password: str) -> User | None:
    """The user for valid email/password credentials, else None (same answer for unknown email or wrong password)."""
    try:
        email = normalize_email(email)
    except ValueError:
        return None
    found = repo.get_credentials(email)
    if not found or not verify_password(password or "", found[1]):
        return None
    repo.record_login(found[0].id)
    return found[0]


def sign_in_external(repo, email: str, name: str, provider: str) -> User:
    """The account for a verified Google/Microsoft identity, created on first sign-in."""
    user = repo.upsert_oauth_user(normalize_email(email), (name or email.split("@")[0]).strip()[:80], provider)
    _adopt_legacy_runs(repo, user)
    return user
