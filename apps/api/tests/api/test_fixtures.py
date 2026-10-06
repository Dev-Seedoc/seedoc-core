# pyright: reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.tenants import MemberRole, Tenant
from seedoc.models.users import User

pytestmark = pytest.mark.usefixtures("postgres")


@pytest.mark.asyncio
async def test_make_factories_and_admin_db(admin_db: AsyncSession, make_tenant, make_user, make_member) -> None:
    """Test that the factories properly insert into the database bypassing RLS."""
    tenant = await make_tenant(name="Fixture Tenant", slug="fixture-tenant")
    user = await make_user(email="fixture@example.com")
    _member = await make_member(tenant, user, MemberRole.ADMIN)

    # Verify admin_db can read them (bypassing RLS since no tenant is set)
    result = await admin_db.execute(select(Tenant).where(Tenant.id == tenant.id))
    fetched_tenant = result.scalar_one_or_none()
    assert fetched_tenant is not None
    assert fetched_tenant.name == "Fixture Tenant"


@pytest.mark.asyncio
async def test_client_as_and_db(client_as, client_other_tenant: AsyncClient, db: AsyncSession) -> None:
    """Test that client_as sets up a client with tenant and user attached."""
    client = await client_as(MemberRole.OWNER)

    # Assert attachments are present
    assert hasattr(client, "tenant")
    assert hasattr(client, "user")
    assert isinstance(client.tenant, Tenant)
    assert isinstance(client.user, User)

    # Assert other_tenant is fully separate
    assert hasattr(client_other_tenant, "tenant")
    assert client.tenant.id != client_other_tenant.tenant.id

    # Try setting tenant in 'db' to test it doesn't crash (actual queries verified in isolation tests)
    from seedoc.db.engine import set_tenant

    await set_tenant(db, client.tenant.id)

    result = await db.execute(select(Tenant).where(Tenant.id == client.tenant.id))
    assert result.scalar_one_or_none() is not None
