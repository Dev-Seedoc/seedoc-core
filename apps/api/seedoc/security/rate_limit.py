"""Failed-login throttling (BUSINESS_RULES §2).

10 failed attempts per key (e-mail or IP hash) within 15 minutes lock that key for 15 minutes → `429 rate_limited`.

State lives in this process's memory. That is enough for the pilot (one API process); with several API processes or
replicas each process counts on its own, so move this to Postgres before scaling out.
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field

from seedoc.errors import AppError, ErrorCode

LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 15 * 60
_PRUNE_THRESHOLD = 10_000


@dataclass
class _KeyState:
    failures: deque[float] = field(default_factory=deque[float])
    locked_until: float = 0.0


_states: dict[str, _KeyState] = {}


def _keys(subject: str, ip_hash: str | None) -> list[str]:
    keys = [f"subject:{subject.lower()}"]
    if ip_hash:
        keys.append(f"ip:{ip_hash}")
    return keys


def _prune(now: float) -> None:
    """Drop keys that are neither locked nor have failures inside the window (bounds memory)."""
    stale = [
        key
        for key, state in _states.items()
        if state.locked_until <= now and (not state.failures or now - state.failures[-1] > LOGIN_WINDOW_SECONDS)
    ]
    for key in stale:
        del _states[key]


def check_login_rate_limit(subject: str, ip_hash: str | None) -> None:
    """Raise `429 rate_limited` if the subject (e-mail, or e.g. `reauth:<user_id>`) or the IP hash is locked."""
    now = time.monotonic()
    for key in _keys(subject, ip_hash):
        state = _states.get(key)
        if state and state.locked_until > now:
            raise AppError(ErrorCode.RATE_LIMITED, details={"retry_after_seconds": math.ceil(state.locked_until - now)})


def record_failed_login(subject: str, ip_hash: str | None) -> None:
    """Count one failure for the subject and the IP hash; the 10th failure in the window starts the lock."""
    now = time.monotonic()
    if len(_states) > _PRUNE_THRESHOLD:
        _prune(now)
    for key in _keys(subject, ip_hash):
        state = _states.setdefault(key, _KeyState())
        while state.failures and now - state.failures[0] > LOGIN_WINDOW_SECONDS:
            state.failures.popleft()
        state.failures.append(now)
        if len(state.failures) >= LOGIN_MAX_FAILURES:
            state.locked_until = now + LOGIN_LOCK_SECONDS
            state.failures.clear()


def reset_failed_login(subject: str) -> None:
    """Clear the subject's failures after a successful login. The IP counter is kept on purpose: an attacker must
    not be able to reset it by logging in to their own account."""
    _states.pop(f"subject:{subject.lower()}", None)


def reset_rate_limits() -> None:
    """Forget all state. Tests only."""
    _states.clear()
