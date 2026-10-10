"""User accounts and profiles. Credentials are never part of these models."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

SEX_OPTIONS = ["Female", "Male", "Non-binary", "Other", "Prefer not to say"]
EDUCATION_OPTIONS = ["Secondary school", "Diploma or certificate", "Bachelor's degree", "Master's degree", "Doctorate",
                     "Other", "Prefer not to say"]
INTEREST_OPTIONS = ["Artificial intelligence", "Enterprise software", "Finance & payments", "Healthcare", "Climate & energy",
                    "Policy & regulation", "Education", "Startups & venture", "Science & research methods", "Economics"]
AUTH_PROVIDER_LABELS = {"password": "email and password", "google": "Google", "microsoft": "Microsoft", "oidc": "single sign-on"}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not EMAIL_PATTERN.match(email) or len(email) > 254:
        raise ValueError("Please enter a valid email address.")
    return email


class UserProfile(BaseModel):
    age: int | None = Field(None, ge=13, le=120)
    sex: str | None = None
    education: str | None = None
    occupation: str = ""
    interests: list[str] = Field(default_factory=list)

    @field_validator("sex")
    @classmethod
    def _sex(cls, value: str | None) -> str | None:
        return value if value in SEX_OPTIONS else None

    @field_validator("education")
    @classmethod
    def _education(cls, value: str | None) -> str | None:
        return value if value in EDUCATION_OPTIONS else None

    @field_validator("occupation")
    @classmethod
    def _occupation(cls, value: str) -> str:
        return (value or "").strip()[:120]

    @field_validator("interests")
    @classmethod
    def _interests(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(i.strip()[:60] for i in value if i and i.strip()))[:20]


class User(BaseModel):
    id: str
    email: str
    name: str
    auth_provider: str = "password"  # password | google | microsoft | oidc
    profile: UserProfile = Field(default_factory=UserProfile)
    created_at: datetime
    last_login_at: datetime | None = None

    @property
    def first_name(self) -> str:
        return (self.name or self.email).split()[0]

    @property
    def initials(self) -> str:
        parts = (self.name or self.email).split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    @property
    def provider_label(self) -> str:
        return AUTH_PROVIDER_LABELS.get(self.auth_provider, self.auth_provider)
