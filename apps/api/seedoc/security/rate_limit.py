"""Rate limiting (throttling) for auth and portal."""

import time
from collections import defaultdict
from dataclasses import dataclass, field

from seedoc.errors import AppError, ErrorCode


@dataclass
class RateLimitWindow:
    count: int = 0
    first_attempt_at: float = field(default_factory=time.monotonic)


_failed_logins_by_email: dict[str, RateLimitWindow] = defaultdict(RateLimitWindow)
_failed_logins_by_ip_hash: dict[str, RateLimitWindow] = defaultdict(RateLimitWindow)

LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60


def _check_and_record(store: dict[str, RateLimitWindow], key: str, max_failures: int, window_seconds: int) -> None:
    now = time.monotonic()
    window = store[key]

    if now - window.first_attempt_at > window_seconds:
        window.count = 1
        window.first_attempt_at = now
    else:
        window.count += 1

    if window.count > max_failures:
        retry_after = int(window_seconds - (now - window.first_attempt_at))
        raise AppError(
            ErrorCode.RATE_LIMITED, "Too many failed login attempts.", details={"retry_after_seconds": retry_after}
        )


def record_failed_login(email: str, ip_hash: str | None) -> None:
    """Record a failed login attempt for the given email and IP hash."""
    _check_and_record(_failed_logins_by_email, email.lower(), LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)
    if ip_hash:
        _check_and_record(_failed_logins_by_ip_hash, ip_hash, LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)


def check_login_rate_limit(email: str, ip_hash: str | None) -> None:
    """Check if the rate limit is currently exceeded (without recording a new attempt)."""
    now = time.monotonic()

    window = _failed_logins_by_email.get(email.lower())
    if window and now - window.first_attempt_at <= LOGIN_WINDOW_SECONDS and window.count >= LOGIN_MAX_FAILURES:
        retry_after = int(LOGIN_WINDOW_SECONDS - (now - window.first_attempt_at))
        raise AppError(
            ErrorCode.RATE_LIMITED, "Too many failed login attempts.", details={"retry_after_seconds": retry_after}
        )

    if ip_hash:
        window = _failed_logins_by_ip_hash.get(ip_hash)
        if window and now - window.first_attempt_at <= LOGIN_WINDOW_SECONDS and window.count >= LOGIN_MAX_FAILURES:
            retry_after = int(LOGIN_WINDOW_SECONDS - (now - window.first_attempt_at))
            raise AppError(
                ErrorCode.RATE_LIMITED, "Too many failed login attempts.", details={"retry_after_seconds": retry_after}
            )


def reset_failed_login(email: str, ip_hash: str | None) -> None:
    """Reset the failed login count for the given email and IP hash."""
    _failed_logins_by_email.pop(email.lower(), None)
    if ip_hash:
        _failed_logins_by_ip_hash.pop(ip_hash, None)
