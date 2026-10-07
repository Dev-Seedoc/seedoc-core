"""Tests for /api/v1/auth endpoints (M0-A6)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.audit import AuditEvent
from seedoc.models.tenants import Invitation, InvitationKind, MemberRole
from seedoc.models.users import PasswordResetToken, UserSession
from seedoc.security.passwords import hash_password
from seedoc.security.sessions import SESSION_COOKIE
from seedoc.security.tokens import hash_token, new_token
from tests.conftest import ClientAs, MakeTenant, MakeUser

pytestmark = pytest.mark.asyncio


async def test_login_success(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    # 1. Setup user
    user = await make_user(email="login@example.com")
    user.password_hash = hash_password("CorrectHorseBatteryStaple123")
    admin_db.add(user)
    await admin_db.commit()

    # 2. Login
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "CorrectHorseBatteryStaple123"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "login@example.com"

    # Check cookie
    assert SESSION_COOKIE in resp.cookies
    token = resp.cookies[SESSION_COOKIE]

    # 3. Use cookie to get_me
    resp2 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token})
    assert resp2.status_code == 200

    # 4. Logout
    resp3 = await client.post("/api/v1/auth/logout", cookies={SESSION_COOKIE: token})
    assert resp3.status_code == 204

    # 5. Token no longer works
    resp4 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token})
    assert resp4.status_code == 401


async def test_login_wrong_password_no_enumeration(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await make_user(email="enum@example.com")
    user.password_hash = hash_password("CorrectPassword123")
    admin_db.add(user)
    await admin_db.commit()

    # Wrong password for existing user
    resp1 = await client.post("/api/v1/auth/login", json={"email": "enum@example.com", "password": "WrongPassword123"})
    assert resp1.status_code == 401
    assert resp1.json()["code"] == "invalid_credentials"

    # User does not exist
    resp2 = await client.post(
        "/api/v1/auth/login", json={"email": "nonexistent@example.com", "password": "WrongPassword123"}
    )
    assert resp2.status_code == 401
    assert resp2.json()["code"] == "invalid_credentials"

    # Check audit log for the failed login of the existing user
    stmt = select(AuditEvent).where(AuditEvent.action == "auth.login_failed")
    event = await admin_db.scalar(stmt)
    assert event is not None
    assert event.entity_id == user.id
    assert event.detail["email"] == "enum@example.com"


async def test_login_throttling(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    user = await make_user(email="throttle@example.com")
    user.password_hash = hash_password("CorrectPassword123")
    admin_db.add(user)
    await admin_db.commit()

    # Fail 10 times
    for _ in range(10):
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "throttle@example.com", "password": "WrongPassword"}
        )
        assert resp.status_code == 401

    # 11th time should be 429
    resp2 = await client.post("/api/v1/auth/login", json={"email": "throttle@example.com", "password": "WrongPassword"})
    assert resp2.status_code == 429
    assert resp2.json()["code"] == "rate_limited"


async def test_expired_and_revoked_session(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    user = await make_user()

    # Create expired session
    token1 = new_token()
    s1 = UserSession(
        user_id=user.id,
        token_hash=hash_token(token1),
        expires_at=datetime.now(UTC) - timedelta(days=1),
        fresh_auth_at=datetime.now(UTC),
    )
    admin_db.add(s1)

    # Create revoked session
    token2 = new_token()
    s2 = UserSession(
        user_id=user.id,
        token_hash=hash_token(token2),
        expires_at=datetime.now(UTC) + timedelta(days=1),
        fresh_auth_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC),
    )
    admin_db.add(s2)
    await admin_db.commit()

    resp1 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token1})
    assert resp1.status_code == 401

    resp2 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token2})
    assert resp2.status_code == 401


async def test_csrf_failure(client_as: ClientAs) -> None:
    # client_as automatically provides a valid session and Origin header
    client_ctx = await client_as(MemberRole.ADMIN)

    # Successful request
    resp1 = await client_ctx.http.post("/api/v1/auth/logout")
    assert resp1.status_code == 204

    client_ctx2 = await client_as(MemberRole.ADMIN)

    # Strip origin
    del client_ctx2.http.headers["Origin"]
    resp2 = await client_ctx2.http.post("/api/v1/auth/logout")
    assert resp2.status_code == 403
    assert resp2.json()["code"] == "csrf_failed"

    # Wrong origin
    client_ctx2.http.headers["Origin"] = "http://evil.com"
    resp3 = await client_ctx2.http.post("/api/v1/auth/logout")
    assert resp3.status_code == 403
    assert resp3.json()["code"] == "csrf_failed"


async def test_password_reset_revokes_sessions(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await make_user()
    user.password_hash = hash_password("OldPassword123")

    # Active session
    token = new_token()
    s = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=1),
        fresh_auth_at=datetime.now(UTC),
    )
    admin_db.add(s)

    # Reset token
    reset_token = new_token()
    rt = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(reset_token),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_db.add(rt)
    await admin_db.commit()

    # Session works before reset
    resp1 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token})
    assert resp1.status_code == 200

    # Perform reset
    resp2 = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": reset_token, "password": "NewPassword123!@#"}
    )
    assert resp2.status_code == 204

    # Session is revoked
    resp3 = await client.get("/api/v1/auth/me", cookies={SESSION_COOKIE: token})
    assert resp3.status_code == 401

    # Audit event
    stmt = select(AuditEvent).where(AuditEvent.action == "auth.password_reset")
    event = await admin_db.scalar(stmt)
    assert event is not None
    assert event.entity_id == user.id


async def test_invitation_single_use_and_expiry(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    tenant = await make_tenant()

    token = new_token()
    inv = Invitation(
        tenant_id=tenant.id,
        email="invitee@example.com",
        kind=InvitationKind.TENANT_MEMBER,
        role=MemberRole.EDITOR,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    admin_db.add(inv)
    await admin_db.commit()

    # Accept invitation
    resp1 = await client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "Invitee", "password": "MySuperSecretPassword123"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["user"]["email"] == "invitee@example.com"

    # Already used
    inv.accepted_at = datetime.now(UTC)
    inv.accepted_by = tenant.id # fake UUID
    await admin_db.commit()
    resp2 = await client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "Invitee", "password": "MySuperSecretPassword123"},
    )
    assert resp2.status_code == 400
    assert resp2.json()["code"] == "invitation_invalid"

    # Expired invitation
    token2 = new_token()
    inv2 = Invitation(
        tenant_id=tenant.id,
        email="invitee2@example.com",
        kind=InvitationKind.TENANT_MEMBER,
        role=MemberRole.EDITOR,
        token_hash=hash_token(token2),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    admin_db.add(inv2)
    await admin_db.commit()

    resp3 = await client.post(
        f"/api/v1/auth/invitations/{token2}/accept",
        json={"full_name": "Invitee 2", "password": "MySuperSecretPassword123"},
    )
    assert resp3.status_code == 400
    assert resp3.json()["code"] == "invitation_invalid"

    # Audit event
    stmt = select(AuditEvent).where(AuditEvent.action == "member.joined")
    event = await admin_db.scalar(stmt)
    assert event is not None
    assert str(inv.id) == event.detail["invitation_id"]


async def test_password_length_validation(client: AsyncClient) -> None:
    # Too short
    resp1 = await client.post("/api/v1/auth/login", json={"email": "test@test.com", "password": ""})
    assert resp1.status_code == 422

    resp2 = await client.post("/api/v1/auth/password-reset/confirm", json={"token": "some-token", "password": "short"})
    assert resp2.status_code == 422
