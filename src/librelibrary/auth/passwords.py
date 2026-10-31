"""Hash and verify passwords with Argon2id."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Return an Argon2id hash of a password."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Say whether a password matches a hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def waste_time_verifying(password: str) -> None:
    """Spend as long as a real check, so timing doesn't reveal unknown users."""
    verify_password(_dummy_hash, password)


def needs_rehash(password_hash: str) -> bool:
    """Say whether a hash uses outdated parameters."""
    return _hasher.check_needs_rehash(password_hash)
