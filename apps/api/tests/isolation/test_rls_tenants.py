"""`tenants`: a member sees only the current tenant row; `seedoc_app` may not create or delete tenants."""

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import Tenant
from tests.isolation.conftest import AsApp, TwoTenants, insert_as


async def test_no_tenant_set_sees_no_tenants(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(Tenant))).all() == []


async def test_sees_only_own_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        ids = (await db.scalars(select(Tenant.id))).all()
    assert ids == [two_tenants.a.tenant_id]


async def test_cannot_update_other_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        stmt = update(Tenant).where(Tenant.id == two_tenants.b.tenant_id).values(name="hijacked").returning(Tenant.id)
        assert (await db.scalars(stmt)).all() == []

    async with get_admin_sessionmaker()() as admin:
        name = await admin.scalar(select(Tenant.name).where(Tenant.id == two_tenants.b.tenant_id))
    assert name != "hijacked"


async def test_can_update_own_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        stmt = update(Tenant).where(Tenant.id == two_tenants.a.tenant_id).values(brand_color="#112233")
        updated = (await db.scalars(stmt.returning(Tenant.id))).all()
    assert updated == [two_tenants.a.tenant_id]


async def test_cannot_insert_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        await insert_as(as_app, two_tenants.a.tenant_id, Tenant(name="Rogue", slug="rogue"))


async def test_cannot_delete_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_app(two_tenants.a.tenant_id) as db:
            await db.execute(delete(Tenant).where(Tenant.id == two_tenants.a.tenant_id))
