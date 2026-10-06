"""Smoke tests for the shared fixtures in `tests/conftest.py`, so a broken fixture fails here and not in 50 places."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.engine import set_tenant
from seedoc.models import MemberRole, Tenant, TenantMember, UserSession
from seedoc.security.sessions import SESSION_COOKIE
from seedoc.security.tokens import hash_token
from tests.conftest import ClientAs, MakeMember, MakeTenant, MakeUser, MemberClient


async def test_factories_persist_rows(
    admin_db: AsyncSession, make_tenant: MakeTenant, make_user: MakeUser, make_member: MakeMember
) -> None:
    tenant = await make_tenant(name="Fixture GmbH")
    user = await make_user()
    await make_member(tenant, user, MemberRole.ADMIN)

    role = await admin_db.scalar(
        select(TenantMember.role).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.id)
    )
    assert role == MemberRole.ADMIN
    assert await admin_db.scalar(select(Tenant.name).where(Tenant.id == tenant.id)) == "Fixture GmbH"


async def test_client_as_logs_in_with_api_token_hashing(client_as: ClientAs, admin_db: AsyncSession) -> None:
    client = await client_as(MemberRole.OWNER)

    assert client.member.role == MemberRole.OWNER
    assert client.http.headers["Origin"] == "http://localhost:5173"
    token = client.http.cookies[SESSION_COOKIE]
    user_id = await admin_db.scalar(select(UserSession.user_id).where(UserSession.token_hash == hash_token(token)))
    assert user_id == client.user.id


async def test_client_other_tenant_is_separate(client_as: ClientAs, client_other_tenant: MemberClient) -> None:
    client = await client_as(MemberRole.OWNER)
    assert client.tenant.id != client_other_tenant.tenant.id
    assert client_other_tenant.member.role == MemberRole.EDITOR


async def test_db_is_rls_scoped(client_as: ClientAs, client_other_tenant: MemberClient, db: AsyncSession) -> None:
    client = await client_as(MemberRole.OWNER)
    async with db.begin():
        await set_tenant(db, client.tenant.id)
        visible = (await db.scalars(select(Tenant.id))).all()
    assert visible == [client.tenant.id]
