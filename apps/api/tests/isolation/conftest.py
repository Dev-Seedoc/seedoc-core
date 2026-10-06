"""Fixtures for the tenant-isolation suite (ARCHITECTURE §7, DATA_MODEL §5).

Every test seeds two tenants through the admin engine (BYPASSRLS) and then acts as `seedoc_app`, the role the
API uses. Rows are unique per test, so tests never depend on each other or on their order.
"""

import hashlib
import secrets
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.base import Base
from seedoc.db.engine import get_admin_sessionmaker, get_app_sessionmaker, set_tenant
from seedoc.models import AuditEvent, Invitation, InvitationKind, MemberRole, Tenant, TenantMember, User

AsApp = Callable[..., AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class TenantRows:
    """Ids of one seeded tenant and the rows that belong to it."""

    tenant_id: UUID
    user_id: UUID
    invitation_id: UUID
    audit_event_id: int


@dataclass(frozen=True)
class TwoTenants:
    a: TenantRows
    b: TenantRows


def random_token_hash() -> bytes:
    """A random sha256 digest, shaped like the stored invitation and session token hashes."""
    return hashlib.sha256(secrets.token_bytes(32)).digest()


def new_invitation(tenant_id: UUID) -> Invitation:
    """An open `tenant_member` invitation for `tenant_id` with a unique e-mail and token."""
    return Invitation(
        tenant_id=tenant_id,
        kind=InvitationKind.TENANT_MEMBER,
        email=f"invitee-{secrets.token_hex(4)}@example.com",
        role=MemberRole.EDITOR,
        token_hash=random_token_hash(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


async def new_user(db: AsyncSession) -> User:
    """Insert a user with a unique e-mail (users are not tenant-scoped)."""
    user = User(email=f"user-{secrets.token_hex(4)}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _seed_tenant(db: AsyncSession, label: str) -> TenantRows:
    tenant = Tenant(name=f"Tenant {label}", slug=f"tenant-{label}-{secrets.token_hex(4)}")
    db.add(tenant)
    user = await new_user(db)
    invitation = new_invitation(tenant.id)
    event = AuditEvent(tenant_id=tenant.id, actor_id=user.id, action="tenant.created", entity="tenant")
    db.add_all([TenantMember(tenant_id=tenant.id, user_id=user.id, role=MemberRole.OWNER), invitation, event])
    await db.flush()
    return TenantRows(tenant.id, user.id, invitation.id, event.id)


@pytest.fixture
async def two_tenants(postgres: dict[str, str]) -> TwoTenants:
    """Tenant A and tenant B, each with an owner, an open invitation and one audit event."""
    async with get_admin_sessionmaker()() as db, db.begin():
        a = await _seed_tenant(db, "a")
        b = await _seed_tenant(db, "b")
    return TwoTenants(a, b)


@pytest.fixture
def as_app() -> AsApp:
    """One transaction as `seedoc_app`, scoped to a tenant if given: `async with as_app(tenant_id) as db:`.

    Commits on success, rolls back if the block raises (so `pytest.raises` around it works).
    """

    @asynccontextmanager
    async def _open(tenant_id: UUID | None = None) -> AsyncGenerator[AsyncSession]:
        async with get_app_sessionmaker()() as db, db.begin():
            if tenant_id is not None:
                await set_tenant(db, tenant_id)
            yield db

    return _open


async def insert_as(as_app: AsApp, tenant_id: UUID, row: Base) -> None:
    """Insert one row as `seedoc_app` scoped to `tenant_id` (raises if RLS or grants reject it)."""
    async with as_app(tenant_id) as db:
        db.add(row)
        await db.flush()
