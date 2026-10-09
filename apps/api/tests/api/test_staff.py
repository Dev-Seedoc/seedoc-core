"""API tests for /api/v1/staff (M0-A8, API.md §6)."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from seedoc.deps import get_ctx, require_role
from seedoc.errors import AppError, ErrorCode
from seedoc.mail.send import send_pending_mail
from seedoc.models.audit import AuditEvent
from seedoc.models.tenants import Invitation, MemberRole, TenantStatus
from seedoc.security.sessions import SESSION_COOKIE
from tests.conftest import ClientAs, ClientStaff, MakeMember, MakeTenant, MakeUser, MemberClient, get_mail_link

pytestmark = pytest.mark.usefixtures("postgres")

STAFF_ROUTES = [
    ("GET", "/api/v1/staff/tenants", None),
    ("POST", "/api/v1/staff/tenants", {"name": "X", "slug": "x-tenant", "owner_email": "o@example.com"}),
    ("GET", f"/api/v1/staff/tenants/{uuid4()}", None),
    ("PATCH", f"/api/v1/staff/tenants/{uuid4()}", {"name": "Y"}),
    ("GET", "/api/v1/staff/users?email=a", None),
]


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


def _slug() -> str:
    return f"t-{uuid4().hex[:10]}"


async def _send(http: Any, method: str, path: str, body: dict[str, str] | None) -> Response:
    return await http.request(method, path, json=body)


# ─────────────────────────── access ───────────────────────────


@pytest.mark.parametrize(("method", "path", "body"), STAFF_ROUTES)
async def test_staff_routes_reject_members(
    client_as: ClientAs, method: str, path: str, body: dict[str, str] | None
) -> None:
    member = await client_as(MemberRole.OWNER)

    response = await _send(member.http, method, path, body)

    assert response.status_code == 403
    assert _error_code(response) == "forbidden"


@pytest.mark.parametrize(("method", "path", "body"), STAFF_ROUTES)
async def test_staff_routes_require_totp_in_session(
    client_staff: ClientStaff, method: str, path: str, body: dict[str, str] | None
) -> None:
    staff = await client_staff(mfa_verified=False)

    response = await _send(staff.http, method, path, body)

    assert response.status_code == 401
    assert _error_code(response) == "mfa_required"


async def test_staff_routes_require_session(client_staff: ClientStaff) -> None:
    staff = await client_staff()
    staff.http.cookies.clear()

    response = await staff.http.get("/api/v1/staff/tenants")

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


# ─────────────────────────── tenants ───────────────────────────


async def test_create_tenant_with_owner_invitation(admin_db: AsyncSession, client_staff: ClientStaff) -> None:
    staff = await client_staff()
    slug = _slug()

    response = await staff.http.post(
        "/api/v1/staff/tenants", json={"name": " Müller Maschinenbau ", "slug": slug, "owner_email": "Chef@Mueller.DE"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Müller Maschinenbau"
    assert body["slug"] == slug
    assert body["status"] == "active"
    assert body["members"] == []
    assert len(body["open_invitations"]) == 1
    assert body["open_invitations"][0]["email"] == "chef@mueller.de"
    assert body["open_invitations"][0]["role"] == "owner"

    invitation = await admin_db.scalar(select(Invitation).where(Invitation.email == "chef@mueller.de"))
    assert invitation is not None
    assert invitation.invited_by == staff.user.id
    assert timedelta(days=6) < invitation.expires_at - datetime.now(UTC) <= timedelta(days=7)
    actions = set(await admin_db.scalars(select(AuditEvent.action).where(AuditEvent.tenant_id == invitation.tenant_id)))
    assert actions == {"tenant.created", "member.invited"}


async def test_create_tenant_mails_the_owner_a_working_invitation(
    client_staff: ClientStaff, outbox: list[EmailMessage]
) -> None:
    staff = await client_staff()
    owner_email = f"owner-{uuid4().hex[:8]}@example.com"

    response = await staff.http.post(
        "/api/v1/staff/tenants", json={"name": "Kraft & <Söhne> GmbH", "slug": _slug(), "owner_email": owner_email}
    )
    await send_pending_mail()

    assert response.status_code == 201
    assert len(outbox) == 1
    mail = outbox[0]
    assert mail["To"] == owner_email
    assert mail["Subject"] == "Einladung zu Kraft & <Söhne> GmbH auf SeeDoc"
    html_part = mail.get_body(preferencelist=("html",))
    assert html_part is not None
    html_body: str = html_part.get_content()
    assert "Kraft &amp; &lt;Söhne&gt; GmbH" in html_body
    assert "<Söhne>" not in html_body
    token = get_mail_link(mail, "/invite/")
    preview = await staff.http.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200
    assert preview.json()["tenant_name"] == "Kraft & <Söhne> GmbH"


async def test_create_tenant_duplicate_slug_sends_no_mail(
    client_staff: ClientStaff, make_tenant: MakeTenant, outbox: list[EmailMessage]
) -> None:
    staff = await client_staff()
    existing = await make_tenant()

    await staff.http.post(
        "/api/v1/staff/tenants", json={"name": "Dup", "slug": existing.slug, "owner_email": "a@example.com"}
    )
    await send_pending_mail()

    assert outbox == []


async def test_create_tenant_duplicate_slug_is_conflict(client_staff: ClientStaff, make_tenant: MakeTenant) -> None:
    staff = await client_staff()
    existing = await make_tenant()

    response = await staff.http.post(
        "/api/v1/staff/tenants", json={"name": "Dup", "slug": existing.slug, "owner_email": "a@example.com"}
    )

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "A", "slug": "Upper-Case", "owner_email": "a@example.com"},
        {"name": "A", "slug": "trailing-", "owner_email": "a@example.com"},
        {"name": "A", "slug": "ok-slug", "owner_email": "not-an-email"},
        {"name": "", "slug": "ok-slug", "owner_email": "a@example.com"},
    ],
)
async def test_create_tenant_validation(client_staff: ClientStaff, body: dict[str, str]) -> None:
    staff = await client_staff()

    response = await staff.http.post("/api/v1/staff/tenants", json=body)

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


async def test_list_tenants_paginates_by_slug(client_staff: ClientStaff, make_tenant: MakeTenant) -> None:
    staff = await client_staff()
    created = {(await make_tenant(slug=_slug())).slug for _ in range(3)}

    seen: list[str] = []
    cursor: str | None = None
    while True:
        params = {"limit": "2", **({"cursor": cursor} if cursor else {})}
        page = (await staff.http.get("/api/v1/staff/tenants", params=params)).json()
        assert len(page["items"]) <= 2
        seen.extend(item["slug"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert created <= set(seen)
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))


async def test_list_tenants_limit_is_bounded(client_staff: ClientStaff) -> None:
    staff = await client_staff()

    response = await staff.http.get("/api/v1/staff/tenants", params={"limit": "201"})

    assert response.status_code == 422


async def test_get_tenant_shows_members_and_counts(
    client_staff: ClientStaff, make_tenant: MakeTenant, make_user: MakeUser, make_member: MakeMember
) -> None:
    staff = await client_staff()
    tenant = await make_tenant(slug=_slug())
    user = await make_user()
    await make_member(tenant, user, MemberRole.ADMIN)

    detail = await staff.http.get(f"/api/v1/staff/tenants/{tenant.id}")
    listing = await staff.http.get("/api/v1/staff/tenants", params={"limit": "200"})

    assert detail.status_code == 200
    assert detail.json()["members"] == [
        {"user_id": str(user.id), "email": user.email, "full_name": user.full_name, "role": "admin"}
    ]
    item = next(i for i in listing.json()["items"] if i["id"] == str(tenant.id))
    assert item["member_count"] == 1


async def test_get_unknown_tenant_is_not_found(client_staff: ClientStaff) -> None:
    staff = await client_staff()

    response = await staff.http.get(f"/api/v1/staff/tenants/{uuid4()}")

    assert response.status_code == 404
    assert _error_code(response) == "not_found"


async def test_update_tenant_name_and_status_are_audited(
    admin_db: AsyncSession, client_staff: ClientStaff, make_tenant: MakeTenant
) -> None:
    staff = await client_staff()
    tenant = await make_tenant(slug=_slug())

    renamed = await staff.http.patch(f"/api/v1/staff/tenants/{tenant.id}", json={"name": "Neuer Name"})
    deactivated = await staff.http.patch(f"/api/v1/staff/tenants/{tenant.id}", json={"status": "inactive"})
    unchanged = await staff.http.patch(f"/api/v1/staff/tenants/{tenant.id}", json={"status": "inactive"})

    assert renamed.json()["name"] == "Neuer Name"
    assert deactivated.json()["status"] == "inactive"
    assert unchanged.status_code == 200
    events = list(await admin_db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id)))
    assert sorted(e.action for e in events) == ["tenant.status_changed", "tenant.updated"]
    status_event = next(e for e in events if e.action == "tenant.status_changed")
    assert status_event.detail == {"from": "active", "to": "inactive"}
    assert status_event.actor_id == staff.user.id


async def test_inactive_tenant_blocks_app_routes_with_403(admin_db: AsyncSession, client_as: ClientAs) -> None:
    member: MemberClient = await client_as(MemberRole.OWNER)
    member.tenant.status = TenantStatus.INACTIVE
    admin_db.add(member.tenant)
    await admin_db.commit()
    token = member.http.cookies[SESSION_COOKIE]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(b"cookie", f"{SESSION_COOKIE}={token}".encode())],
            "path_params": {"tenant_id": str(member.tenant.id)},
            "client": ("127.0.0.1", 1234),
        }
    )
    request.state.request_id = "test"

    ctx = await get_ctx(request)

    assert ctx.role is MemberRole.OWNER
    assert ctx.is_tenant_active is False
    with pytest.raises(AppError) as error:
        await require_role(MemberRole.EDITOR)(ctx)
    assert error.value.code is ErrorCode.FORBIDDEN


# ─────────────────────────── users ───────────────────────────


async def test_find_users_by_email_fragment(client_staff: ClientStaff, make_user: MakeUser) -> None:
    staff = await client_staff()
    marker = uuid4().hex[:8]
    match = await make_user(email=f"jana.{marker}@kunde.de")
    await make_user(email=f"other-{uuid4().hex[:8]}@kunde.de")

    response = await staff.http.get("/api/v1/staff/users", params={"email": marker.upper()})

    assert response.status_code == 200
    page = response.json()
    assert [item["id"] for item in page["items"]] == [str(match.id)]
    assert page["items"][0]["has_totp"] is False
    assert page["next_cursor"] is None


async def test_find_users_treats_wildcards_literally(client_staff: ClientStaff) -> None:
    staff = await client_staff()

    response = await staff.http.get("/api/v1/staff/users", params={"email": "%"})

    assert response.json()["items"] == []
