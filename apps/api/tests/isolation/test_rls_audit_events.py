"""`audit_events`: tenant-isolated and append-only for `seedoc_app` (select + insert, never update or delete)."""

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from seedoc.models import AuditEvent
from tests.isolation.conftest import AsApp, TwoTenants, insert_as


async def test_no_tenant_set_sees_no_events(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(AuditEvent))).all() == []


async def test_sees_only_own_events(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        rows = (await db.scalars(select(AuditEvent))).all()
    assert {row.tenant_id for row in rows} == {two_tenants.a.tenant_id}
    assert two_tenants.a.audit_event_id in {row.id for row in rows}


async def test_can_insert_own_event(two_tenants: TwoTenants, as_app: AsApp) -> None:
    a = two_tenants.a.tenant_id
    async with as_app(a) as db:
        db.add(AuditEvent(tenant_id=a, action="document.created", entity="document"))
        await db.flush()


async def test_cannot_insert_event_for_other_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await insert_as(
            as_app,
            two_tenants.a.tenant_id,
            AuditEvent(tenant_id=two_tenants.b.tenant_id, action="document.created", entity="document"),
        )


@pytest.mark.parametrize("owner", ["a", "b"])
async def test_cannot_update_any_event(two_tenants: TwoTenants, as_app: AsApp, owner: str) -> None:
    event_id = getattr(two_tenants, owner).audit_event_id
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_app(two_tenants.a.tenant_id) as db:
            await db.execute(update(AuditEvent).where(AuditEvent.id == event_id).values(action="tampered"))


@pytest.mark.parametrize("owner", ["a", "b"])
async def test_cannot_delete_any_event(two_tenants: TwoTenants, as_app: AsApp, owner: str) -> None:
    event_id = getattr(two_tenants, owner).audit_event_id
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_app(two_tenants.a.tenant_id) as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
