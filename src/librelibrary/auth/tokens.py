"""Create personal access tokens and hash them for storage.

Tokens are long and random, so a plain SHA-256 is the right hash. Slow password
hashes exist to protect guessable secrets, and these aren't guessable.
"""

import hashlib
import secrets

TOKEN_PREFIX = "llpat_"  # noqa: S105
_DISPLAY_LENGTH = len(TOKEN_PREFIX) + 6


def hash_token(plaintext: str) -> str:
    """Return the stored form of a token."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def new_token() -> tuple[str, str, str]:
    """Return a new token, its hash, and a short prefix that is safe to display."""
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return plaintext, hash_token(plaintext), plaintext[:_DISPLAY_LENGTH]
