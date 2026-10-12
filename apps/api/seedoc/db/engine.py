"""Engines and session factories.

Two engines (ARCHITECTURE §7):
- app engine as `seedoc_app` — RLS enforced; used by /auth, /app, /portal, /operator.
- admin engine as `seedoc_admin` — BYPASSRLS; used only by staff routes and jobs.
Migrations use `seedoc_owner` through Alembic, never through this module.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from seedoc.config import get_settings


@lru_cache
def get_app_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_admin_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_admin_url, pool_pre_ping=True)


@lru_cache
def get_app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False)


@lru_cache
def get_admin_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_admin_engine(), expire_on_commit=False)


async def set_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    """Scope RLS to one tenant for the current transaction. Must run inside `async with db.begin():`."""
    await db.execute(text("select set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": str(tenant_id)})


@asynccontextmanager
async def tenant_transaction(db: AsyncSession, tenant_id: UUID | None) -> AsyncGenerator[UUID]:
    """One transaction scoped to the tenant of an /app request: `async with tenant_transaction(db, ctx.tenant_id)
    as tenant_id:`. Commits when the block ends, rolls back if it raises. Queries inside still filter by the yielded
    `tenant_id` explicitly; RLS is the second line of defence, not the only one."""
    if tenant_id is None:  # an /app route always has one; require_role() has already checked membership
        raise RuntimeError("tenant_transaction needs the request's tenant_id")
    async with db.begin():
        await set_tenant(db, tenant_id)
        yield tenant_id


async def dispose_engines() -> None:
    for factory in (get_app_engine, get_admin_engine):
        if factory.cache_info().currsize:
            await factory().dispose()
