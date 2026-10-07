"""FastAPI dependencies shared by all routers."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.db.engine import get_admin_sessionmaker, get_app_sessionmaker
from seedoc.errors import AppError, ErrorCode
from seedoc.models.tenants import MemberRole
from seedoc.security.crypto import get_ip_hash

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


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_app` (RLS enforced). Services open the transaction themselves."""
    async with get_app_sessionmaker()() as session:
        yield session


async def get_admin_db() -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_admin` (BYPASSRLS). Only for staff routers — never /app, /portal or /operator."""
    async with get_admin_sessionmaker()() as session:
        yield session


async def get_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> RequestContext:  # noqa: B008
    import contextlib

    from sqlalchemy import select

    from seedoc.models.operators import OperatorMember
    from seedoc.models.tenants import TenantMember
    from seedoc.models.users import User
    from seedoc.security.sessions import SESSION_COOKIE, get_and_touch_session

    client_ip = request.client.host if request.client else None
    ip_hash = get_ip_hash(client_ip, get_settings().ip_hash_pepper) if client_ip else None

    user_id = None
    session_id = None
    fresh_auth_at = None
    is_staff = False
    role = None
    operator_org_ids = ()

    tenant_id_str = request.path_params.get("tenant_id")
    tenant_id = None
    if tenant_id_str:
        with contextlib.suppress(ValueError):
            tenant_id = UUID(tenant_id_str)

    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session_data = await get_and_touch_session(db, token)
        if session_data:
            user_id = session_data["user_id"]
            session_id = session_data["session_id"]
            fresh_auth_at = session_data["fresh_auth_at"]

            stmt = select(User.is_staff).where(User.id == user_id)
            is_staff = await db.scalar(stmt) or False

            if tenant_id:
                stmt_role = select(TenantMember.role).where(
                    TenantMember.user_id == user_id, TenantMember.tenant_id == tenant_id
                )
                role = await db.scalar(stmt_role)

            stmt_ops = select(OperatorMember.operator_org_id).where(OperatorMember.user_id == user_id)
            result = await db.execute(stmt_ops)
            operator_org_ids = tuple(row[0] for row in result.all())

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
    )


DbSession = Annotated[AsyncSession, Depends(get_db)]
AdminDbSession = Annotated[AsyncSession, Depends(get_admin_db)]
Ctx = Annotated[RequestContext, Depends(get_ctx)]


def require_role(min_role: MemberRole) -> Callable[[RequestContext], Awaitable[RequestContext]]:
    """Tenant routes: no session → 401, not a member → 404 (existence not revealed), role too low → 403."""

    async def dependency(ctx: Ctx) -> RequestContext:
        if ctx.user_id is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        if ctx.role is None:
            raise AppError(ErrorCode.NOT_FOUND)
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
