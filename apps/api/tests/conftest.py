"""Shared fixtures. Tests that touch the database run against a real Postgres (testcontainers), never SQLite."""

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import alembic.config
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Settings are read from the environment, so test defaults must exist before seedoc is imported.
_TEST_ENV = {
    "ENVIRONMENT": "local",
    "APP_URL": "http://localhost:5173",
    "APP_HOST": "localhost",
    "DATABASE_URL": "postgresql+asyncpg://seedoc_app:seedoc_app@127.0.0.1:1/seedoc",
    "DATABASE_ADMIN_URL": "postgresql+asyncpg://seedoc_admin:seedoc_admin@127.0.0.1:1/seedoc",
    "DATABASE_OWNER_URL": "postgresql+asyncpg://seedoc_owner:seedoc_owner@127.0.0.1:1/seedoc",
    "S3_ENDPOINT": "http://localhost:9000",
    "S3_REGION": "eu-central-1",
    "S3_BUCKET": "seedoc-test",
    "S3_ACCESS_KEY": "test",
    "S3_SECRET_KEY": "test",
    "IP_HASH_PEPPER": "dGVzdC1wZXBwZXItdGVzdC1wZXBwZXItdGVzdC1wZXA=",
    "TOTP_ENCRYPTION_KEY": "dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHQ=",
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value

from seedoc.config import get_settings  # noqa: E402
from seedoc.db import engine as db_engine  # noqa: E402
from seedoc.main import create_app  # noqa: E402
from seedoc.models.tenants import MemberRole, Tenant, TenantMember, TenantStatus  # noqa: E402
from seedoc.models.users import User, UserSession  # noqa: E402
from seedoc.security.rate_limit import reset_rate_limits  # noqa: E402
from seedoc.security.sessions import SESSION_COOKIE  # noqa: E402
from seedoc.security.tokens import hash_token, new_token  # noqa: E402
from seedoc.security.totp import encrypt_totp_secret, new_totp_secret  # noqa: E402

ROLES_SQL = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init" / "01-roles.sql"
POSTGRES_IMAGE = "pgvector/pgvector:pg16"


def _reset_caches() -> None:
    get_settings.cache_clear()
    for factory in (
        db_engine.get_app_engine,
        db_engine.get_admin_engine,
        db_engine.get_app_sessionmaker,
        db_engine.get_admin_sessionmaker,
    ):
        factory.cache_clear()


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres() -> Iterator[dict[str, str]]:
    """Postgres 16 + pgvector with the three SeeDoc roles. Points the settings at it for the session."""
    if not _docker_available():
        pytest.skip("Docker is not running; database tests need testcontainers")

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(POSTGRES_IMAGE, username="postgres", password="postgres", dbname="seedoc") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)

        with psycopg.connect(f"postgresql://postgres:postgres@{host}:{port}/seedoc", autocommit=True) as conn:
            conn.execute(ROLES_SQL.read_text(encoding="utf-8").encode())

        urls = {
            f"DATABASE{suffix}_URL": f"postgresql+asyncpg://seedoc_{role}:seedoc_{role}@{host}:{port}/seedoc"
            for suffix, role in (("", "app"), ("_ADMIN", "admin"), ("_OWNER", "owner"))
        }
        previous = {key: os.environ[key] for key in urls}
        os.environ.update(urls)
        _reset_caches()

        # Round trip before any connection exists: proves every downgrade works, then leaves the schema at head.
        for step in ("head", "base", "head"):
            alembic.config.main(argv=["--raiseerr", "upgrade" if step == "head" else "downgrade", step])

        yield urls
        os.environ.update(previous)
        _reset_caches()


@pytest.fixture(autouse=True)
def reset_login_throttle() -> Iterator[None]:
    """The login throttle is process memory; without this, failures in one test would lock out the next."""
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture
def unreachable_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app engine at a port where nothing listens, even if the session Postgres is running."""
    monkeypatch.setenv("DATABASE_URL", _TEST_ENV["DATABASE_URL"])
    _reset_caches()
    yield
    _reset_caches()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://localhost") as http:
        yield http
    await db_engine.dispose_engines()
    _reset_caches()


@pytest.fixture
async def db(postgres: dict[str, str]) -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_app` (RLS enforced) — the role the API uses. Call `set_tenant` inside a transaction."""
    async with db_engine.get_app_sessionmaker()() as session:
        yield session


@pytest.fixture
async def admin_db(postgres: dict[str, str]) -> AsyncIterator[AsyncSession]:
    """Session as `seedoc_admin` (BYPASSRLS). For seeding test data and for staff/job code — never for /app code."""
    async with db_engine.get_admin_sessionmaker()() as session:
        yield session


class MakeTenant(Protocol):
    async def __call__(
        self, name: str = "Acme GmbH", slug: str | None = None, status: TenantStatus = TenantStatus.ACTIVE
    ) -> Tenant: ...


class MakeUser(Protocol):
    async def __call__(
        self, email: str | None = None, full_name: str = "Max Mustermann", is_staff: bool = False
    ) -> User: ...


class MakeMember(Protocol):
    async def __call__(self, tenant: Tenant, user: User, role: MemberRole) -> TenantMember: ...


@dataclass(frozen=True)
class MemberClient:
    """An HTTP client logged in as `user`, who is a member of `tenant` with `member.role`."""

    http: AsyncClient
    tenant: Tenant
    user: User
    member: TenantMember


class ClientAs(Protocol):
    async def __call__(self, role: MemberRole) -> MemberClient: ...


@pytest.fixture
def make_tenant(admin_db: AsyncSession) -> MakeTenant:
    """`await make_tenant(...)` → a committed `Tenant` with a unique slug (written via the admin role)."""

    async def factory(
        name: str = "Acme GmbH", slug: str | None = None, status: TenantStatus = TenantStatus.ACTIVE
    ) -> Tenant:
        tenant = Tenant(name=name, slug=slug or f"acme-{uuid4().hex[:8]}", status=status)
        admin_db.add(tenant)
        await admin_db.commit()
        await admin_db.refresh(tenant)
        return tenant

    return factory


@pytest.fixture
def make_user(admin_db: AsyncSession) -> MakeUser:
    """`await make_user(...)` → a committed `User` with a unique e-mail and no usable password."""

    async def factory(email: str | None = None, full_name: str = "Max Mustermann", is_staff: bool = False) -> User:
        user = User(email=email or f"user-{uuid4().hex[:8]}@example.com", full_name=full_name, is_staff=is_staff)
        admin_db.add(user)
        await admin_db.commit()
        await admin_db.refresh(user)
        return user

    return factory


@pytest.fixture
def make_member(admin_db: AsyncSession) -> MakeMember:
    """`await make_member(tenant, user, role)` → a committed `TenantMember`."""

    async def factory(tenant: Tenant, user: User, role: MemberRole) -> TenantMember:
        member = TenantMember(tenant_id=tenant.id, user_id=user.id, role=role)
        admin_db.add(member)
        await admin_db.commit()
        await admin_db.refresh(member)
        return member

    return factory


@pytest.fixture
async def client_as(
    admin_db: AsyncSession, make_tenant: MakeTenant, make_user: MakeUser, make_member: MakeMember
) -> AsyncIterator[ClientAs]:
    """`await client_as(role)` → a `MemberClient` logged in as a fresh member of a fresh tenant.

    The session row is created with `security.tokens` (the same hashing the API uses) and the client sends the
    `Origin` header the CSRF check expects. All clients are closed after the test.
    """
    clients: list[AsyncClient] = []
    app = create_app()
    origin = get_settings().app_url

    async def factory(role: MemberRole) -> MemberClient:
        tenant = await make_tenant()
        user = await make_user()
        member = await make_member(tenant, user, role)

        token = new_token()
        admin_db.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=1),
                fresh_auth_at=datetime.now(UTC),
            )
        )
        await admin_db.commit()

        http = AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://localhost",
            headers={"Origin": origin},
            cookies={SESSION_COOKIE: token},
        )
        clients.append(http)
        return MemberClient(http=http, tenant=tenant, user=user, member=member)

    yield factory

    for http in clients:
        await http.aclose()


@pytest.fixture
async def client_other_tenant(client_as: ClientAs) -> MemberClient:
    """An editor of a *different* tenant — use it to prove another tenant's ids return 404."""
    return await client_as(MemberRole.EDITOR)


@dataclass(frozen=True)
class StaffClient:
    """An HTTP client logged in as a staff `user` whose TOTP secret is `totp_secret` (plain, for `pyotp`)."""

    http: AsyncClient
    user: User
    totp_secret: str
    session_token: str


class ClientStaff(Protocol):
    async def __call__(self, mfa_verified: bool = True, totp_enabled: bool = True) -> StaffClient: ...


@pytest.fixture
async def client_staff(admin_db: AsyncSession, make_user: MakeUser) -> AsyncIterator[ClientStaff]:
    """`await client_staff()` → a staff user with TOTP set up and a session that passed TOTP (staff routes work).

    `mfa_verified=False` gives a session that has not passed TOTP yet (staff routes answer `401 mfa_required`);
    `totp_enabled=False` gives a staff user who has not enrolled at all.
    """
    clients: list[AsyncClient] = []
    app = create_app()
    origin = get_settings().app_url

    async def factory(mfa_verified: bool = True, totp_enabled: bool = True) -> StaffClient:
        user = await make_user(is_staff=True)
        secret = new_totp_secret()
        now = datetime.now(UTC)
        if totp_enabled:
            user.totp_secret_enc = encrypt_totp_secret(secret)
            user.totp_enabled_at = now
        token = new_token()
        admin_db.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + timedelta(days=1),
                fresh_auth_at=now,
                mfa_verified_at=now if mfa_verified else None,
            )
        )
        await admin_db.commit()

        http = AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://localhost",
            headers={"Origin": origin},
            cookies={SESSION_COOKIE: token},
        )
        clients.append(http)
        return StaffClient(http=http, user=user, totp_secret=secret, session_token=token)

    yield factory

    for http in clients:
        await http.aclose()
