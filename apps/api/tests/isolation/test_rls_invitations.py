"""`invitations`: tenant A can never select, insert, update or delete tenant B's invitations."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import Invitation
from tests.isolation.conftest import AsApp, TwoTenants, insert_as, new_invitation


async def test_no_tenant_set_sees_no_invitations(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(Invitation))).all() == []


async def test_sees_only_own_invitations(two_tenants: TwoTenants, as_app: AsApp) -> None:
    async with as_app(two_tenants.a.tenant_id) as db:
        rows = (await db.scalars(select(Invitation))).all()
    assert {row.tenant_id for row in rows} == {two_tenants.a.tenant_id}
    assert two_tenants.a.invitation_id in {row.id for row in rows}


async def test_cannot_insert_invitation_for_other_tenant(two_tenants: TwoTenants, as_app: AsApp) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await insert_as(as_app, two_tenants.a.tenant_id, new_invitation(two_tenants.b.tenant_id))


async def test_cannot_update_or_delete_other_tenants_invitations(two_tenants: TwoTenants, as_app: AsApp) -> None:
    b_invitation = two_tenants.b.invitation_id
    async with as_app(two_tenants.a.tenant_id) as db:
        updated = await db.scalars(
            update(Invitation)
            .where(Invitation.id == b_invitation)
            .values(revoked_at=datetime.now(UTC))
            .returning(Invitation.id)
        )
        assert updated.all() == []
        deleted = await db.scalars(delete(Invitation).where(Invitation.id == b_invitation).returning(Invitation.id))
        assert deleted.all() == []

    async with get_admin_sessionmaker()() as admin:
        revoked_at = await admin.scalar(select(Invitation.revoked_at).where(Invitation.id == b_invitation))
        still_there = await admin.scalar(select(Invitation.id).where(Invitation.id == b_invitation))
    assert revoked_at is None
    assert still_there == b_invitation


async def test_own_invitations_are_writable(two_tenants: TwoTenants, as_app: AsApp) -> None:
    """Guards against a policy that denies everything."""
    a = two_tenants.a.tenant_id
    async with as_app(a) as db:
        invitation = new_invitation(a)
        db.add(invitation)
        await db.flush()
        revoked = await db.scalars(
            update(Invitation)
            .where(Invitation.id == invitation.id)
            .values(revoked_at=datetime.now(UTC))
            .returning(Invitation.id)
        )
        assert revoked.all() == [invitation.id]
        removed = await db.scalars(delete(Invitation).where(Invitation.id == invitation.id).returning(Invitation.id))
        assert removed.all() == [invitation.id]
