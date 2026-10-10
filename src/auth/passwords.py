"""Password hashing with scrypt (standard library). Only the salted hash is stored, never the password."""
from __future__ import annotations

import hashlib
import hmac
import secrets

MIN_PASSWORD_LENGTH = 8
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 64


def validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > 256:
        raise ValueError("Passwords are limited to 256 characters.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
