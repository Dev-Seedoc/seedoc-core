"""FastAPI dependencies shared by all routers."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.db.engine import get_admin_sessionmaker, get_app_sessionmaker, set_tenant
from seedoc.errors import AppError, ErrorCode
from seedoc.models.operators import OperatorMember
from seedoc.models.tenants import MemberRole, Tenant, TenantStatus
from seedoc.models.users import User
from seedoc.security.crypto import get_ip_hash
from seedoc.security.sessions import SESSION_COOKIE, get_and_touch_session

FRESH_AUTH_TTL = timedelta(minutes=30)
_ROLE_RANK = {MemberRole.EDITOR: 1, MemberRole.ADMIN: 2, MemberRole.OWNER: 3}


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID | None  # None for anonymous portal
    tenant_id: UUID | None  # set for /app routes and after portal/operator resolution
    role: MemberRole | None  # tenant role for /app routes
    is_staff: bool
    session_id: UUID | None
    fresh_auth_at: datetime | None
    portal_session_id: UUID | None
    operator_org_ids: tuple[UUID, ...]
    ip_hash: str | None  # sha256(IP_HASH_PEPPER || ip), never the raw IP
    request_id: str
    mfa_verified_at: datetime | None = None  # staff: TOTP verified in this session
    is_tenant_active: bool = True  # False when the {tenant_id} of an /app route belongs to an inactive tenant


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_app` (RLS enforced). Services open the transaction themselves."""
    async with get_app_sessionmaker()() as session:
        yield session


async def get_admin_db() -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_admin` (BYPASSRLS). Only for staff routers — never /app, /portal or /operator."""
    async with get_admin_sessionmaker()() as session:
        yield session


async def get_ctx(request: Request) -> RequestContext:
    """Build the request context from the `seedoc_session` cookie and the `{tenant_id}` path parameter.

    Runs in its own short transaction (not the request's `DbSession`), so the session touch is committed and the
    services can still open their own transaction on `DbSession`.
    """
    client_ip = request.client.host if request.client else None
    ip_hash = get_ip_hash(client_ip, get_settings().ip_hash_pepper) if client_ip else None
    tenant_id = _parse_uuid(request.path_params.get("tenant_id"))

    user_id: UUID | None = None
    session_id: UUID | None = None
    fresh_auth_at: datetime | None = None
    mfa_verified_at: datetime | None = None
    is_staff = False
    is_tenant_active = True
    role: MemberRole | None = None
    operator_org_ids: tuple[UUID, ...] = ()

    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with get_app_sessionmaker()() as db, db.begin():
            session = await get_and_touch_session(db, token)
            if session is not None:
                user_id = session.user_id
                session_id = session.id
                fresh_auth_at = session.fresh_auth_at
                mfa_verified_at = session.mfa_verified_at
                is_staff = bool(await db.scalar(select(User.is_staff).where(User.id == user_id)))
                if tenant_id is not None:
                    # member_tenants() is SECURITY DEFINER: tenant_members is under RLS and no tenant is set yet.
                    role_value = await db.scalar(
                        text("select role from member_tenants(:user_id) where tenant_id = :tenant_id"),
                        {"user_id": user_id, "tenant_id": tenant_id},
                    )
                    role = MemberRole(role_value) if role_value is not None else None
                    if role is not None:
                        # Members may read their own tenant row under RLS once the tenant is set.
                        await set_tenant(db, tenant_id)
                        status = await db.scalar(select(Tenant.status).where(Tenant.id == tenant_id))
                        is_tenant_active = status is TenantStatus.ACTIVE
                org_ids = await db.scalars(
                    select(OperatorMember.operator_org_id).where(OperatorMember.user_id == user_id)
                )
                operator_org_ids = tuple(org_ids)

    return RequestContext(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        is_staff=is_staff,
        session_id=session_id,
        fresh_auth_at=fresh_auth_at,
        portal_session_id=None,
        operator_org_ids=operator_org_ids,
        ip_hash=ip_hash,
        request_id=request.state.request_id,
        mfa_verified_at=mfa_verified_at,
        is_tenant_active=is_tenant_active,
    )


def _parse_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


DbSession = Annotated[AsyncSession, Depends(get_db)]
AdminDbSession = Annotated[AsyncSession, Depends(get_admin_db)]
Ctx = Annotated[RequestContext, Depends(get_ctx)]


def require_role(min_role: MemberRole) -> Callable[[RequestContext], Awaitable[RequestContext]]:
    """Tenant routes: no session → 401, not a member → 404 (existence not revealed), inactive tenant → 403
    (BUSINESS_RULES §1), role too low → 403."""

    async def dependency(ctx: Ctx) -> RequestContext:
        if ctx.user_id is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        if ctx.role is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if not ctx.is_tenant_active:
            raise AppError(ErrorCode.FORBIDDEN, "tenant is inactive")
        if _ROLE_RANK[ctx.role] < _ROLE_RANK[min_role]:
            raise AppError(ErrorCode.FORBIDDEN)
        return ctx

    return dependency


async def require_fresh_auth(ctx: Ctx) -> RequestContext:
    """Password re-entered within the last 30 minutes (BUSINESS_RULES §1)."""
    if ctx.user_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if ctx.fresh_auth_at is None or datetime.now(UTC) - ctx.fresh_auth_at > FRESH_AUTH_TTL:
        raise AppError(ErrorCode.FRESH_AUTH_REQUIRED)
    return ctx


async def require_staff(ctx: Ctx) -> RequestContext:
    """Staff routes (API.md §6): no session → 401, not staff → 403, TOTP not verified in this session → 401
    `mfa_required`."""
    if ctx.user_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if not ctx.is_staff:
        raise AppError(ErrorCode.FORBIDDEN)
    if ctx.mfa_verified_at is None:
        raise AppError(ErrorCode.MFA_REQUIRED)
    return ctx


StaffCtx = Annotated[RequestContext, Depends(require_staff)]
