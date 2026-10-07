"""API tests for /api/v1/auth (M0-A6, API.md §2, BUSINESS_RULES §2)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from seedoc.config import get_settings
from seedoc.deps import get_ctx
from seedoc.models.audit import AuditEvent
from seedoc.models.operators import OperatorMember, OperatorOrg, OperatorRole
from seedoc.models.tenants import Invitation, InvitationKind, MemberRole, Tenant, TenantMember
from seedoc.models.users import PasswordResetToken, User, UserSession
from seedoc.security.passwords import hash_password
from seedoc.security.sessions import SESSION_COOKIE
from seedoc.security.tokens import hash_token, new_token
from tests.conftest import ClientAs, MakeMember, MakeTenant, MakeUser

pytestmark = pytest.mark.usefixtures("postgres")

PASSWORD = "CorrectHorseBattery1"
OTHER_PASSWORD = "AnotherLongPassword9"


def _cookie(token: str) -> dict[str, str]:
    """Headers for a browser request with the session cookie (Origin satisfies the CSRF check)."""
    return {"Cookie": f"{SESSION_COOKIE}={token}", "Origin": get_settings().app_url}


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def _user_with_password(admin_db: AsyncSession, make_user: MakeUser, email: str | None = None) -> User:
    user = await make_user(email=email)
    user.password_hash = hash_password(PASSWORD)
    await admin_db.commit()
    return user


async def _session_token(admin_db: AsyncSession, user: User, **overrides: datetime | None) -> str:
    token = new_token()
    now = datetime.now(UTC)
    values: dict[str, datetime | None] = {
        "expires_at": now + timedelta(days=1),
        "last_seen_at": now,
        "fresh_auth_at": now,
        **overrides,
    }
    admin_db.add(UserSession(user_id=user.id, token_hash=hash_token(token), **values))
    await admin_db.commit()
    return token


async def _invitation(
    admin_db: AsyncSession, tenant: Tenant, email: str, **overrides: object
) -> tuple[Invitation, str]:
    token = new_token()
    fields: dict[str, object] = {
        "tenant_id": tenant.id,
        "kind": InvitationKind.TENANT_MEMBER,
        "email": email,
        "role": MemberRole.EDITOR,
        "token_hash": hash_token(token),
        "expires_at": datetime.now(UTC) + timedelta(days=7),
        **overrides,
    }
    invitation = Invitation(**fields)
    admin_db.add(invitation)
    await admin_db.commit()
    return invitation, token


# ─────────────────────────── login / me / logout ───────────────────────────


async def test_login_sets_cookie_and_me_lists_memberships(
    admin_db: AsyncSession, make_user: MakeUser, make_tenant: MakeTenant, make_member: MakeMember, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user, "login@example.com")
    tenant = await make_tenant(name="Beta AG")
    await make_member(tenant, user, MemberRole.ADMIN)

    response = await client.post("/api/v1/auth/login", json={"email": "Login@Example.com ", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "login@example.com"
    assert body["memberships"] == [{"tenant_id": str(tenant.id), "tenant_name": "Beta AG", "role": "admin"}]
    assert body["is_staff"] is False
    assert body["mfa_verified"] is False
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie

    token = response.cookies[SESSION_COOKIE]
    me = await client.get("/api/v1/auth/me", headers=_cookie(token))
    assert me.status_code == 200
    assert me.json()["memberships"][0]["role"] == "admin"


async def test_logout_revokes_session(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    user = await _user_with_password(admin_db, make_user)
    token = await _session_token(admin_db, user)

    assert (await client.post("/api/v1/auth/logout", headers=_cookie(token))).status_code == 204
    response = await client.get("/api/v1/auth/me", headers=_cookie(token))

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


async def test_login_rotates_existing_session(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    user = await _user_with_password(admin_db, make_user)
    old_token = await _session_token(admin_db, user)

    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}, headers=_cookie(old_token)
    )

    assert response.status_code == 200
    assert response.cookies[SESSION_COOKIE] != old_token
    assert (await client.get("/api/v1/auth/me", headers=_cookie(old_token))).status_code == 401


async def test_me_without_session_is_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


async def test_login_wrong_password_and_unknown_email_look_the_same(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)

    wrong = await client.post("/api/v1/auth/login", json={"email": user.email, "password": OTHER_PASSWORD})
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert _error_code(wrong) == _error_code(unknown) == "invalid_credentials"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert SESSION_COOKIE not in wrong.cookies


async def test_failed_login_is_audited_without_tenant(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)

    await client.post("/api/v1/auth/login", json={"email": user.email, "password": OTHER_PASSWORD})

    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "auth.login_failed", AuditEvent.entity_id == user.id)
    )
    assert event is not None
    assert event.tenant_id is None
    assert event.ip_hash is not None
    assert "password" not in event.detail


async def test_login_throttled_after_10_failures_even_with_correct_password(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)
    for _ in range(10):
        failed = await client.post("/api/v1/auth/login", json={"email": user.email, "password": OTHER_PASSWORD})
        assert failed.status_code == 401

    blocked = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

    assert blocked.status_code == 429
    assert _error_code(blocked) == "rate_limited"
    assert 0 < blocked.json()["error"]["details"]["retry_after_seconds"] <= 15 * 60


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, id="absolute-expired"),
        pytest.param({"last_seen_at": datetime.now(UTC) - timedelta(hours=13)}, id="idle-expired"),
        pytest.param({"revoked_at": datetime.now(UTC)}, id="revoked"),
    ],
)
async def test_invalid_session_is_unauthenticated(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient, overrides: dict[str, datetime]
) -> None:
    user = await _user_with_password(admin_db, make_user)
    token = await _session_token(admin_db, user, **overrides)

    response = await client.get("/api/v1/auth/me", headers=_cookie(token))

    assert response.status_code == 401


async def test_session_touch_is_committed(admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient) -> None:
    user = await _user_with_password(admin_db, make_user)
    old = datetime.now(UTC) - timedelta(hours=2)
    token = await _session_token(admin_db, user, last_seen_at=old)

    assert (await client.get("/api/v1/auth/me", headers=_cookie(token))).status_code == 200

    last_seen = await admin_db.scalar(
        select(UserSession.last_seen_at).where(UserSession.token_hash == hash_token(token))
    )
    assert last_seen is not None
    assert last_seen > old


# ─────────────────────────── request context ───────────────────────────


async def test_get_ctx_resolves_role_only_for_own_tenant(
    admin_db: AsyncSession, make_user: MakeUser, make_tenant: MakeTenant, make_member: MakeMember
) -> None:
    user = await _user_with_password(admin_db, make_user)
    own, other = await make_tenant(), await make_tenant()
    await make_member(own, user, MemberRole.ADMIN)
    token = await _session_token(admin_db, user)

    def request_for(tenant_id: str) -> Request:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "headers": [(b"cookie", f"{SESSION_COOKIE}={token}".encode())],
                "path_params": {"tenant_id": tenant_id},
                "client": ("127.0.0.1", 1234),
            }
        )
        request.state.request_id = "test"
        return request

    own_ctx = await get_ctx(request_for(str(own.id)))
    other_ctx = await get_ctx(request_for(str(other.id)))

    assert own_ctx.user_id == user.id
    assert own_ctx.role is MemberRole.ADMIN
    assert other_ctx.user_id == user.id
    assert other_ctx.role is None


# ─────────────────────────── CSRF ───────────────────────────


async def test_csrf_requires_matching_origin(client_as: ClientAs) -> None:
    ok_client = await client_as(MemberRole.ADMIN)
    assert (await ok_client.http.post("/api/v1/auth/logout")).status_code == 204

    member = await client_as(MemberRole.ADMIN)
    del member.http.headers["Origin"]
    missing = await member.http.post("/api/v1/auth/logout")
    member.http.headers["Origin"] = "http://evil.example"
    wrong = await member.http.post("/api/v1/auth/logout")

    assert missing.status_code == wrong.status_code == 403
    assert _error_code(missing) == _error_code(wrong) == "csrf_failed"
    assert wrong.headers["X-Request-ID"]


# ─────────────────────────── reauth ───────────────────────────


async def test_reauthenticate_refreshes_fresh_auth(admin_db: AsyncSession, client_as: ClientAs) -> None:
    member = await client_as(MemberRole.OWNER)
    member.user.password_hash = hash_password(PASSWORD)
    admin_db.add(member.user)
    await admin_db.execute(
        update(UserSession)
        .where(UserSession.user_id == member.user.id)
        .values(fresh_auth_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await admin_db.commit()

    wrong = await member.http.post("/api/v1/auth/reauth", json={"password": OTHER_PASSWORD})
    right = await member.http.post("/api/v1/auth/reauth", json={"password": PASSWORD})

    assert wrong.status_code == 401
    assert _error_code(wrong) == "invalid_credentials"
    assert right.status_code == 204
    fresh = await admin_db.scalar(select(UserSession.fresh_auth_at).where(UserSession.user_id == member.user.id))
    assert fresh is not None
    assert datetime.now(UTC) - fresh < timedelta(minutes=1)


async def test_reauthenticate_requires_session(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/reauth", json={"password": PASSWORD})

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


# ─────────────────────────── password reset ───────────────────────────


async def test_request_password_reset_always_202_and_creates_token_only_for_known_email(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)

    known = await client.post("/api/v1/auth/password-reset", json={"email": user.email})
    unknown = await client.post("/api/v1/auth/password-reset", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    count = await admin_db.scalar(
        select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    assert count == 1


async def test_password_reset_changes_password_revokes_sessions_and_is_single_use(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)
    session_token = await _session_token(admin_db, user)
    reset_token = new_token()
    admin_db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_token(reset_token), expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
    )
    await admin_db.commit()
    body = {"token": reset_token, "password": OTHER_PASSWORD}

    first = await client.post("/api/v1/auth/password-reset/confirm", json=body)
    again = await client.post("/api/v1/auth/password-reset/confirm", json=body)

    assert first.status_code == 204
    assert again.status_code == 410
    assert _error_code(again) == "invitation_invalid"
    assert (await client.get("/api/v1/auth/me", headers=_cookie(session_token))).status_code == 401
    old_login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    new_login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": OTHER_PASSWORD})
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "auth.password_reset", AuditEvent.entity_id == user.id)
    )
    assert event is not None
    assert event.actor_id == user.id


async def test_password_reset_expired_token_is_invalid(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)
    reset_token = new_token()
    admin_db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_token(reset_token), expires_at=datetime.now(UTC) - timedelta(minutes=1)
        )
    )
    await admin_db.commit()

    response = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": reset_token, "password": OTHER_PASSWORD}
    )

    assert response.status_code == 410


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/auth/login", {"email": "a@example.com", "password": ""}),
        ("/api/v1/auth/login", {"email": "a@example.com", "password": "x" * 129}),
        ("/api/v1/auth/password-reset/confirm", {"token": "t", "password": "elevenchars"}),
        ("/api/v1/auth/password-reset/confirm", {"token": "t", "password": "x" * 129}),
    ],
)
async def test_password_length_is_validated(client: AsyncClient, path: str, body: dict[str, str]) -> None:
    response = await client.post(path, json=body)

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


# ─────────────────────────── invitations ───────────────────────────


async def test_get_invitation_preview(admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient) -> None:
    tenant = await make_tenant(name="Gamma GmbH")
    _, token = await _invitation(admin_db, tenant, "new@example.com")

    response = await client.get(f"/api/v1/auth/invitations/{token}")

    assert response.status_code == 200
    assert response.json() == {
        "kind": "tenant_member",
        "tenant_name": "Gamma GmbH",
        "operator_org_name": None,
        "email": "new@example.com",
        "has_account": False,
    }


async def test_accept_invitation_creates_user_membership_and_session(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    tenant = await make_tenant()
    invitation, token = await _invitation(admin_db, tenant, "Invitee@Example.com", role=MemberRole.ADMIN)

    response = await client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "Erika Muster", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "invitee@example.com"
    assert body["user"]["full_name"] == "Erika Muster"
    assert body["memberships"] == [{"tenant_id": str(tenant.id), "tenant_name": tenant.name, "role": "admin"}]
    assert SESSION_COOKIE in response.cookies
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "member.joined", AuditEvent.entity_id == invitation.id)
    )
    assert event is not None
    assert event.tenant_id == tenant.id


async def test_accept_invitation_is_single_use(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, "once@example.com")
    body = {"password": PASSWORD}

    first = await client.post(f"/api/v1/auth/invitations/{token}/accept", json=body)
    second = await client.post(f"/api/v1/auth/invitations/{token}/accept", json=body)

    assert first.status_code == 200
    assert second.status_code == 410
    assert _error_code(second) == "invitation_invalid"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, id="expired"),
        pytest.param({"revoked_at": datetime.now(UTC)}, id="revoked"),
    ],
)
async def test_closed_invitation_is_invalid(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient, overrides: dict[str, datetime]
) -> None:
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, f"closed-{uuid4().hex[:6]}@example.com", **overrides)

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    accept = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={"password": PASSWORD})

    assert preview.status_code == accept.status_code == 410


async def test_unknown_invitation_is_invalid(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/auth/invitations/{new_token()}")

    assert response.status_code == 410
    assert _error_code(response) == "invitation_invalid"


async def test_accept_invitation_for_new_user_requires_password(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, "nopw@example.com")

    response = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={})

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


async def test_accept_invitation_existing_account_needs_its_password(
    admin_db: AsyncSession, make_user: MakeUser, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, user.email)

    without = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={})
    wrong = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={"password": OTHER_PASSWORD})
    right = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={"password": PASSWORD})

    assert without.status_code == wrong.status_code == 401
    assert _error_code(without) == "invalid_credentials"
    assert SESSION_COOKIE not in without.cookies
    assert right.status_code == 200
    assert right.json()["memberships"][0]["tenant_id"] == str(tenant.id)


async def test_accept_invitation_logged_in_as_invitee_needs_no_password(
    admin_db: AsyncSession, make_user: MakeUser, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    user = await _user_with_password(admin_db, make_user)
    session_token = await _session_token(admin_db, user)
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, user.email)

    response = await client.post(f"/api/v1/auth/invitations/{token}/accept", json={}, headers=_cookie(session_token))

    assert response.status_code == 200


async def test_accept_invitation_logged_in_as_someone_else_is_forbidden(
    admin_db: AsyncSession, make_tenant: MakeTenant, client_as: ClientAs
) -> None:
    other = await client_as(MemberRole.EDITOR)
    tenant = await make_tenant()
    _, token = await _invitation(admin_db, tenant, "someone-else@example.com")

    response = await other.http.post(f"/api/v1/auth/invitations/{token}/accept", json={"password": PASSWORD})

    assert response.status_code == 403
    assert _error_code(response) == "forbidden"
    member = await admin_db.scalar(select(TenantMember).where(TenantMember.tenant_id == tenant.id))
    assert member is None


async def test_operator_invitation_first_member_is_admin(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient
) -> None:
    tenant = await make_tenant()
    org = OperatorOrg(name="Betreiber KG")
    admin_db.add(org)
    await admin_db.commit()
    operator = {"kind": InvitationKind.OPERATOR, "role": None, "operator_org_id": org.id, "customer_id": uuid4()}
    _, first_token = await _invitation(admin_db, tenant, "op1@example.com", **operator)
    _, second_token = await _invitation(admin_db, tenant, "op2@example.com", **operator)

    first = await client.post(f"/api/v1/auth/invitations/{first_token}/accept", json={"password": PASSWORD})
    second = await client.post(f"/api/v1/auth/invitations/{second_token}/accept", json={"password": PASSWORD})

    assert first.status_code == second.status_code == 200
    assert first.json()["operator_orgs"] == [{"operator_org_id": str(org.id), "name": "Betreiber KG", "role": "admin"}]
    assert second.json()["operator_orgs"][0]["role"] == "member"
    roles = await admin_db.scalars(select(OperatorMember.role).where(OperatorMember.operator_org_id == org.id))
    assert sorted(roles) == sorted([OperatorRole.ADMIN, OperatorRole.MEMBER])
