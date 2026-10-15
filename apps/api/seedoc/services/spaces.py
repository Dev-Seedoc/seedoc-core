"""Spaces (API.md §3.2). The reference pattern for /app services: one function per operation_id, each opens its
own tenant-scoped transaction, filters every query by the tenant and raises `AppError`, never HTTP errors."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.models.documents import Space
from seedoc.schemas.common import Page
from seedoc.schemas.spaces import SpaceCreate, SpaceRead, SpaceUpdate
from seedoc.services.library import get_sort_key, get_space


async def list_spaces(db: AsyncSession, ctx: RequestContext) -> Page[SpaceRead]:
    """All spaces of the tenant by name (German-friendly order). A tenant has a handful, so the list is never paged
    (`next_cursor` null)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        spaces = await db.scalars(select(Space).where(Space.tenant_id == tenant_id))
        ordered = sorted(spaces, key=lambda space: (get_sort_key(space.name), space.id))
        return Page(items=[SpaceRead.model_validate(space) for space in ordered], next_cursor=None)


async def create_space(db: AsyncSession, ctx: RequestContext, body: SpaceCreate) -> SpaceRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        space = Space(tenant_id=tenant_id, name=body.name)
        db.add(space)
        await db.flush()
        await db.refresh(space)  # created_at comes from the database
        await write_audit_event(db, ctx, "space.created", "space", space.id)
        return SpaceRead.model_validate(space)


async def update_space(db: AsyncSession, ctx: RequestContext, space_id: UUID, body: SpaceUpdate) -> SpaceRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        space = await get_space(db, tenant_id, space_id)
        if body.name is not None:
            space.name = body.name
        return SpaceRead.model_validate(space)
