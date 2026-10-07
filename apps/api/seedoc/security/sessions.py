"""Login sessions (ARCHITECTURE §8, BUSINESS_RULES §2).

The cookie `seedoc_session` carries a random token; the table `sessions` stores only its hash. A session is valid
until it is revoked, 12 h after it was last seen (idle) or 30 days after it was created (absolute).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.users import UserSession
from seedoc.security.tokens import hash_token, new_token

SESSION_COOKIE = "seedoc_session"
SESSION_IDLE_TTL = timedelta(hours=12)
SESSION_ABSOLUTE_TTL = timedelta(days=30)


async def create_session(db: AsyncSession, user_id: UUID, user_agent: str | None) -> str:
    """Insert a new session and return the raw token (sent to the client once, never stored)."""
    token = new_token()
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            user_agent=user_agent,
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_ABSOLUTE_TTL,
            fresh_auth_at=now,
        )
    )
    await db.flush()
    return token


async def get_and_touch_session(db: AsyncSession, token: str) -> UserSession | None:
    """Return the valid session for `token` and update `last_seen_at`; None if unknown, revoked or expired.

    Must run inside a transaction that is committed, otherwise the touch is lost.
    """
    if not token.isascii():
        return None
    session = await db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if (
        session is None
        or session.revoked_at is not None
        or now >= session.expires_at
        or now >= session.last_seen_at + SESSION_IDLE_TTL
    ):
        return None
    session.last_seen_at = now
    return session


async def revoke_session(db: AsyncSession, session_id: UUID) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    """Revoke every active session of a user (password reset)."""
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
