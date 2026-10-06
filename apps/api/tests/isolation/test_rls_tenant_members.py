"""`tenant_members`: tenant A can never select, insert, update or delete tenant B's memberships."""

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import MemberRole, TenantMember
from tests.isolation.conftest import AsApp, TwoTenants, insert_as, new_user


async def test_no_tenant_set_sees_no_members(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(TenantMember))).all() == []


async def test_sees_only_own_members(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        rows = (await db.scalars(select(TenantMember))).all()
    assert {row.tenant_id for row in rows} == {two_tenants.a.tenant_id}
    assert two_tenants.a.user_id in {row.user_id for row in rows}


async def test_cannot_insert_member_into_other_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with get_admin_sessionmaker()() as admin, admin.begin():
        user_id = (await new_user(admin)).id

    with pytest.raises(DBAPIError, match="row-level security"):
        await insert_as(
            as_app,
            two_tenants.a.tenant_id,
            TenantMember(tenant_id=two_tenants.b.tenant_id, user_id=user_id, role=MemberRole.ADMIN),
        )


async def test_cannot_update_or_delete_other_tenants_members(two_tenants: TwoTenants, as_app: AsApp) -> None:
    b = two_tenants.b
    async with as_app(two_tenants.a.tenant_id) as db:
        updated = await db.scalars(
            update(TenantMember)
            .where(TenantMember.tenant_id == b.tenant_id)
            .values(role=MemberRole.EDITOR)
            .returning(TenantMember.user_id)
        )
        assert updated.all() == []
        deleted = await db.scalars(
            delete(TenantMember).where(TenantMember.tenant_id == b.tenant_id).returning(TenantMember.user_id)
        )
        assert deleted.all() == []

    async with get_admin_sessionmaker()() as admin:
        role = await admin.scalar(
            select(TenantMember.role).where(TenantMember.tenant_id == b.tenant_id, TenantMember.user_id == b.user_id)
        )
    assert role == MemberRole.OWNER


async def test_own_tenant_members_are_writable(two_tenants: TwoTenants, as_app: AsApp) -> None:
    """Guards against a policy that denies everything, which would make the tests above pass for the wrong reason."""
    async with get_admin_sessionmaker()() as admin, admin.begin():
        user_id = (await new_user(admin)).id

    a = two_tenants.a.tenant_id
    async with as_app(a) as db:
        db.add(TenantMember(tenant_id=a, user_id=user_id, role=MemberRole.EDITOR))
        await db.flush()
        changed = await db.scalars(
            update(TenantMember)
            .where(TenantMember.tenant_id == a, TenantMember.user_id == user_id)
            .values(role=MemberRole.ADMIN)
            .returning(TenantMember.user_id)
        )
        assert changed.all() == [user_id]
        removed = await db.scalars(
            delete(TenantMember)
            .where(TenantMember.tenant_id == a, TenantMember.user_id == user_id)
            .returning(TenantMember.user_id)
        )
        assert removed.all() == [user_id]


async def test_member_tenants_reads_across_rls(two_tenants: TwoTenants, as_app: AsApp) -> None:
    """`member_tenants()` is SECURITY DEFINER: it must work before any tenant is set, and only for that user."""
    async with as_app() as db:
        rows = (
            await db.execute(
                text("select tenant_id, role from member_tenants(:user_id)"), {"user_id": two_tenants.a.user_id}
            )
        ).all()
    assert [(row.tenant_id, row.role) for row in rows] == [(two_tenants.a.tenant_id, MemberRole.OWNER.value)]
