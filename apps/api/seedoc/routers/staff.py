"""Staff console routes (API.md §6). Staff + TOTP-verified session, admin DB engine."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from seedoc.deps import AdminDbSession, StaffCtx
from seedoc.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from seedoc.schemas.staff import (
    StaffTenantCreate,
    StaffTenantListItem,
    StaffTenantRead,
    StaffTenantUpdate,
    StaffUserListItem,
)
from seedoc.services import staff as staff_service

router = APIRouter(prefix="/staff", tags=["staff"])

Cursor = Annotated[str | None, Query()]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]


@router.get("/tenants")
async def staff_list_tenants(
    db: AdminDbSession, ctx: StaffCtx, cursor: Cursor = None, limit: Limit = DEFAULT_PAGE_LIMIT
) -> Page[StaffTenantListItem]:
    return await staff_service.staff_list_tenants(db, ctx, cursor, limit)


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def staff_create_tenant(body: StaffTenantCreate, db: AdminDbSession, ctx: StaffCtx) -> StaffTenantRead:
    return await staff_service.staff_create_tenant(db, ctx, body)


@router.get("/tenants/{tenant_id}")
async def staff_get_tenant(tenant_id: UUID, db: AdminDbSession, ctx: StaffCtx) -> StaffTenantRead:
    return await staff_service.staff_get_tenant(db, ctx, tenant_id)


@router.patch("/tenants/{tenant_id}")
async def staff_update_tenant(
    tenant_id: UUID, body: StaffTenantUpdate, db: AdminDbSession, ctx: StaffCtx
) -> StaffTenantRead:
    return await staff_service.staff_update_tenant(db, ctx, tenant_id, body)


@router.get("/users")
async def staff_find_users(
    db: AdminDbSession,
    ctx: StaffCtx,
    email: Annotated[str, Query(min_length=1, max_length=254)],
    cursor: Cursor = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
) -> Page[StaffUserListItem]:
    return await staff_service.staff_find_users(db, ctx, email, cursor, limit)
