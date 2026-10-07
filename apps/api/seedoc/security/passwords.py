"""Password hashing with Argon2id."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against an Argon2id hash. Returns True if valid."""
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
