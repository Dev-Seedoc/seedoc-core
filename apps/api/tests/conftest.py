# pyright: reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false
"""Shared fixtures. Tests that touch the database run against a real Postgres (testcontainers), never SQLite."""

import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import alembic.config
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

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
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from seedoc.config import get_settings  # noqa: E402
from seedoc.db import engine as db_engine  # noqa: E402
from seedoc.main import create_app  # noqa: E402
from seedoc.models.tenants import MemberRole, Tenant, TenantMember, TenantStatus  # noqa: E402
from seedoc.models.users import User, UserSession  # noqa: E402

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
async def db() -> AsyncIterator[AsyncSession]:
    """Database session authenticated as the seedoc_app role.
    Use this for testing services and business logic with RLS applied.
    """
    factory = db_engine.get_app_sessionmaker()
    async with factory() as session:
        yield session


@pytest.fixture
async def admin_db() -> AsyncIterator[AsyncSession]:
    """Database session authenticated as the seedoc_admin role (BYPASSRLS).
    Use this for staff routes, jobs, or when a factory needs to bypass RLS.
    """
    factory = db_engine.get_admin_sessionmaker()
    async with factory() as session:
        yield session


@pytest.fixture
def make_tenant(admin_db: AsyncSession):
    """Factory to create and persist a Tenant in the database. Returns a coroutine."""

    async def factory(
        name: str = "Acme Corp", slug: str | None = None, status: TenantStatus = TenantStatus.ACTIVE
    ) -> Tenant:
        slug = slug or f"acme-{uuid4().hex[:8]}"
        t = Tenant(name=name, slug=slug, status=status)
        admin_db.add(t)
        await admin_db.commit()
        await admin_db.refresh(t)
        return t

    return factory


@pytest.fixture
def make_user(admin_db: AsyncSession):
    """Factory to create and persist a User in the database. Returns a coroutine."""

    async def factory(email: str | None = None, full_name: str = "John Doe", is_staff: bool = False) -> User:
        email = email or f"user-{uuid4().hex[:8]}@example.com"
        u = User(email=email, full_name=full_name, is_staff=is_staff, password_hash="dummy")
        admin_db.add(u)
        await admin_db.commit()
        await admin_db.refresh(u)
        return u

    return factory


@pytest.fixture
def make_member(admin_db: AsyncSession):
    """Factory to create a TenantMember linking a User and a Tenant with a given role. Returns a coroutine."""

    async def factory(tenant: Tenant, user: User, role: MemberRole) -> TenantMember:
        tm = TenantMember(tenant_id=tenant.id, user_id=user.id, role=role)
        admin_db.add(tm)
        await admin_db.commit()
        await admin_db.refresh(tm)
        return tm

    return factory


@pytest.fixture
def client_as(admin_db: AsyncSession, make_tenant, make_user, make_member):
    """Factory to get an authenticated AsyncClient for a member with a specific role.
    It provisions a tenant, user, membership, and a valid session.

    The returned client will have `client.tenant` and `client.user` available.
    """

    async def factory(role: MemberRole) -> AsyncClient:
        tenant = await make_tenant()
        user = await make_user()
        await make_member(tenant, user, role)

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).digest()

        # Valid session expiring in 1 day
        expires_at = datetime.now(UTC) + timedelta(days=1)
        session = UserSession(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
        admin_db.add(session)
        await admin_db.commit()

        app = create_app()
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        http = AsyncClient(transport=transport, base_url="http://localhost")
        http.cookies.set("seedoc_session", token)

        # Attach entities to the client for easy access in tests
        http.tenant = tenant  # type: ignore
        http.user = user  # type: ignore

        return http

    return factory


@pytest.fixture
async def client_other_tenant(client_as) -> AsyncClient:
    """Fixture to get an authenticated AsyncClient for a DIFFERENT tenant than the primary one.
    Useful for testing tenant isolation (e.g., verifying 404s on another tenant's data).
    """
    return await client_as(MemberRole.EDITOR)
