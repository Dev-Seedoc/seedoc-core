"""Staff console (API.md §6). Runs on the admin engine (`seedoc_admin`, BYPASSRLS) — callers pass `AdminDbSession`."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.mail.send import MailTemplate, get_app_link, send_email
from seedoc.models.tenants import Invitation, InvitationKind, MemberRole, Tenant, TenantMember
from seedoc.models.users import User
from seedoc.schemas.common import Page
from seedoc.schemas.staff import (
    StaffTenantCreate,
    StaffTenantInvitationRead,
    StaffTenantListItem,
    StaffTenantMemberRead,
    StaffTenantRead,
    StaffTenantUpdate,
    StaffUserListItem,
)
from seedoc.security.tokens import hash_token, new_token

INVITATION_TTL = timedelta(days=7)


async def staff_list_tenants(
    db: AsyncSession, ctx: RequestContext, cursor: str | None, limit: int
) -> Page[StaffTenantListItem]:
    """All tenants ordered by slug; `cursor` is the last slug of the previous page."""
    member_count = (
        select(func.count())
        .select_from(TenantMember)
        .where(TenantMember.tenant_id == Tenant.id)
        .correlate(Tenant)
        .scalar_subquery()
    )
    query = select(Tenant, member_count).order_by(Tenant.slug).limit(limit + 1)
    if cursor is not None:
        query = query.where(Tenant.slug > cursor)
    async with db.begin():
        rows = (await db.execute(query)).all()

    items = [
        StaffTenantListItem(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status,
            member_count=count,
            created_at=tenant.created_at,
        )
        for tenant, count in rows[:limit]
    ]
    return Page(items=items, next_cursor=items[-1].slug if len(rows) > limit else None)


async def staff_create_tenant(db: AsyncSession, ctx: RequestContext, body: StaffTenantCreate) -> StaffTenantRead:
    """Create the tenant and an owner invitation (7 days); the invitation mail is sent after the commit."""
    owner_email = body.owner_email.strip().lower()
    try:
        async with db.begin():
            if await db.scalar(select(Tenant.id).where(Tenant.slug == body.slug)) is not None:
                raise AppError(ErrorCode.CONFLICT, "slug already in use", details={"field": "slug"})
            tenant = Tenant(name=body.name.strip(), slug=body.slug)
            db.add(tenant)
            await db.flush()

            token = new_token()
            invitation = Invitation(
                tenant_id=tenant.id,
                kind=InvitationKind.TENANT_MEMBER,
                email=owner_email,
                role=MemberRole.OWNER,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + INVITATION_TTL,
                invited_by=ctx.user_id,
            )
            db.add(invitation)
            await db.flush()

            await write_audit_event(
                db, ctx, "tenant.created", "tenant", tenant.id, {"slug": tenant.slug}, tenant_id=tenant.id
            )
            await write_audit_event(
                db, ctx, "member.invited", "invitation", invitation.id, {"role": "owner"}, tenant_id=tenant.id
            )
            created = await _read_tenant(db, tenant.id)
    except IntegrityError as exc:  # two staff members creating the same slug at the same moment
        raise AppError(ErrorCode.CONFLICT, "slug already in use", details={"field": "slug"}) from exc

    send_email(
        MailTemplate.INVITATION_TENANT_MEMBER,
        owner_email,
        {"tenant_name": created.name, "invitation_url": get_app_link(f"/invite/{token}")},
    )
    return created


async def staff_get_tenant(db: AsyncSession, ctx: RequestContext, tenant_id: UUID) -> StaffTenantRead:
    async with db.begin():
        return await _read_tenant(db, tenant_id)


async def staff_update_tenant(
    db: AsyncSession, ctx: RequestContext, tenant_id: UUID, body: StaffTenantUpdate
) -> StaffTenantRead:
    async with db.begin():
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise AppError(ErrorCode.NOT_FOUND)

        if body.name is not None and body.name.strip() != tenant.name:
            tenant.name = body.name.strip()
            await write_audit_event(
                db, ctx, "tenant.updated", "tenant", tenant.id, {"fields": ["name"]}, tenant_id=tenant.id
            )
        if body.status is not None and body.status != tenant.status:
            previous = tenant.status
            tenant.status = body.status
            await write_audit_event(
                db,
                ctx,
                "tenant.status_changed",
                "tenant",
                tenant.id,
                {"from": previous.value, "to": body.status.value},
                tenant_id=tenant.id,
            )
        await db.flush()
        return await _read_tenant(db, tenant.id)


async def staff_find_users(
    db: AsyncSession, ctx: RequestContext, email: str, cursor: str | None, limit: int
) -> Page[StaffUserListItem]:
    """Users whose e-mail contains `email` (case-insensitive), ordered by e-mail; `cursor` is the last e-mail."""
    pattern = "%" + email.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    query = select(User).where(User.email.ilike(pattern, escape="\\")).order_by(User.email).limit(limit + 1)
    if cursor is not None:
        query = query.where(User.email > cursor)
    async with db.begin():
        users = list(await db.scalars(query))

    items = [
        StaffUserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_staff=user.is_staff,
            has_totp=user.totp_enabled_at is not None,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )
        for user in users[:limit]
    ]
    return Page(items=items, next_cursor=items[-1].email if len(users) > limit else None)


async def _read_tenant(db: AsyncSession, tenant_id: UUID) -> StaffTenantRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(ErrorCode.NOT_FOUND)
    await db.refresh(tenant)  # server-side defaults and `updated_at` after an update

    member_rows = await db.execute(
        select(TenantMember.user_id, User.email, User.full_name, TenantMember.role)
        .join(User, User.id == TenantMember.user_id)
        .where(TenantMember.tenant_id == tenant_id)
        .order_by(User.email)
    )
    invitations = await db.scalars(
        select(Invitation)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.kind == InvitationKind.TENANT_MEMBER,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > func.now(),
        )
        .order_by(Invitation.created_at)
    )
    return StaffTenantRead(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        members=[
            StaffTenantMemberRead(user_id=user_id, email=email, full_name=full_name, role=role)
            for user_id, email, full_name, role in member_rows
        ],
        open_invitations=[
            StaffTenantInvitationRead(
                id=invitation.id,
                email=invitation.email,
                role=invitation.role,
                expires_at=invitation.expires_at,
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ],
    )
