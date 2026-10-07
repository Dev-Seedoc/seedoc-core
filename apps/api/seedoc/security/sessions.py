"""Login sessions (ARCHITECTURE §8). M0-A6 adds creation, lookup, idle/absolute expiry and rotation here."""

from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.users import UserSession
from seedoc.security.tokens import hash_token, new_token

SESSION_COOKIE = "seedoc_session"
SESSION_IDLE_TTL = timedelta(hours=12)
SESSION_ABSOLUTE_TTL = timedelta(days=30)


class SessionData(TypedDict):
    user_id: UUID
    session_id: UUID
    fresh_auth_at: datetime | None


async def create_session(db: AsyncSession, user_id: UUID, user_agent: str | None) -> str:
    """Create a new session and return the raw session token."""
    token = new_token()
    now = datetime.now(UTC)
    stmt = (
        insert(UserSession)
        .values(
            user_id=user_id,
            token_hash=hash_token(token),
            user_agent=user_agent,
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_ABSOLUTE_TTL,
            fresh_auth_at=now,
        )
        .returning(UserSession.id)
    )
    await db.execute(stmt)
    return token


async def get_and_touch_session(db: AsyncSession, token: str) -> SessionData | None:
    """Look up a session by token, verify it's valid, update last_seen_at, and return data.
    Returns None if the session is invalid, expired, or revoked.
    """
    now = datetime.now(UTC)
    stmt = select(UserSession).where(UserSession.token_hash == hash_token(token))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        return None

    if session.revoked_at is not None:
        return None

    expires_at = session.expires_at.replace(tzinfo=UTC) if session.expires_at.tzinfo is None else session.expires_at
    if now > expires_at:
        return None

    last_seen_at = (
        session.last_seen_at.replace(tzinfo=UTC) if session.last_seen_at.tzinfo is None else session.last_seen_at
    )
    if now > last_seen_at + SESSION_IDLE_TTL:
        return None

    # Touch the session
    session.last_seen_at = now

    return {
        "user_id": session.user_id,
        "session_id": session.id,
        "fresh_auth_at": (
            session.fresh_auth_at.replace(tzinfo=UTC)
            if session.fresh_auth_at and session.fresh_auth_at.tzinfo is None
            else session.fresh_auth_at
        ),
    }


async def rotate_session(db: AsyncSession, old_token: str) -> str | None:
    """Rotate the session token (e.g. on login or privilege escalation).
    Returns the new token, or None if the old session is invalid.
    """
    now = datetime.now(UTC)
    stmt = select(UserSession).where(UserSession.token_hash == hash_token(old_token))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        return None

    expires_at = session.expires_at.replace(tzinfo=UTC) if session.expires_at.tzinfo is None else session.expires_at
    if now > expires_at:
        return None

    last_seen_at = (
        session.last_seen_at.replace(tzinfo=UTC) if session.last_seen_at.tzinfo is None else session.last_seen_at
    )
    if now > last_seen_at + SESSION_IDLE_TTL:
        return None

    new_raw_token = new_token()
    session.token_hash = hash_token(new_raw_token)
    session.last_seen_at = now
    session.fresh_auth_at = now
    return new_raw_token


async def revoke_session(db: AsyncSession, token: str) -> None:
    """Revoke a specific session by token."""
    stmt = (
        update(UserSession)
        .where(UserSession.token_hash == hash_token(token))
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(stmt)


async def revoke_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    """Revoke all active sessions for a user (e.g. on password reset)."""
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(stmt)
