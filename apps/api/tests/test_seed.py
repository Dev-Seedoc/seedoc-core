"""`make seed` (M0-A10): idempotent demo data whose printed credentials really work."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models.tenants import Tenant
from seedoc.seed import DEMO_TENANT_SLUG, DEMO_USERS, SeedResult, seed_demo_data

pytestmark = pytest.mark.usefixtures("postgres")


async def _seed(reset_passwords: bool = False) -> SeedResult:
    """Like `make seed`: a fresh admin-engine session per run."""
    async with get_admin_sessionmaker()() as db:
        return await seed_demo_data(db, reset_passwords=reset_passwords)


async def test_seed_is_idempotent_and_credentials_log_in(admin_db: AsyncSession, client: AsyncClient) -> None:
    first = await _seed()
    second = await _seed()

    assert first.tenant_created is True
    assert second.tenant_created is False
    assert all(user.password for user in first.users)
    assert all(user.password is None for user in second.users)
    staff = next(user for user in first.users if user.label == "staff")
    assert staff.totp_uri is not None
    assert staff.totp_uri.startswith(f"otpauth://totp/SeeDoc:{staff.email}?")
    assert all(user.totp_uri is None for user in second.users)
    tenants = await admin_db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
    assert tenants == 1

    for seeded, demo in zip(first.users, DEMO_USERS, strict=True):
        response = await client.post("/api/v1/auth/login", json={"email": seeded.email, "password": seeded.password})
        assert response.status_code == 200, seeded.email
        me = response.json()
        assert me["is_staff"] is demo.is_staff
        roles = [membership["role"] for membership in me["memberships"]]
        assert roles == ([demo.role.value] if demo.role else [])

    reset = await _seed(reset_passwords=True)
    owner_old, owner_new = first.users[0], reset.users[0]
    assert owner_new.password is not None
    assert owner_new.password != owner_old.password
    old_login = await client.post("/api/v1/auth/login", json={"email": owner_old.email, "password": owner_old.password})
    new_login = await client.post("/api/v1/auth/login", json={"email": owner_new.email, "password": owner_new.password})
    assert old_login.status_code == 401
    assert new_login.status_code == 200
