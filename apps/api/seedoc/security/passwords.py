"""Password hashing with Argon2id (`argon2-cffi` defaults)."""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("seedoc-dummy-password-for-timing")


def verify_password_or_dummy(password_hash: str | None, password: str) -> bool:
    """Verify against the user's hash, or against a dummy hash when there is none.

    Unknown e-mails and users without a password then cost the same Argon2 time as real ones, so response timing
    does not reveal which e-mail addresses have an account.
    """
    if password_hash is None:
        verify_password(_dummy_hash(), password)
        return False
    return verify_password(password_hash, password)
