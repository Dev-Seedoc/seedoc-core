"""Opaque secret tokens (sessions, invitations, password resets, portal sessions) and the public QR tokens.

The raw token goes to the client exactly once; the database stores only `hash_token(token)` (ARCHITECTURE §8,
BUSINESS_RULES §2). Every place that creates or looks up a token must use these two functions, so the hashing
can never drift between the code that writes a token and the code (or test) that reads it.
"""

import hashlib
import secrets

TOKEN_BYTES = 32


def new_token() -> str:
    """32 random bytes, base64url without padding (43 characters)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """sha256 of the token string as stored in `*.token_hash` columns."""
    return hashlib.sha256(token.encode("ascii")).digest()


def new_public_token() -> str:
    """A QR token for `machines.public_token` / `deliveries.public_token` (BUSINESS_RULES §11): 32 random bytes,
    base64url without padding. Stored as is (it is printed on labels, not a secret) and **never changed** — the
    `/m/{token}` and `/s/{token}` URLs are a permanent contract (AGENTS.md rule 8)."""
    return secrets.token_urlsafe(TOKEN_BYTES)
