"""Shared fixtures. Tests that touch the database run against a real Postgres (testcontainers), never SQLite."""

import asyncio
import os
import re
import sys
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import alembic.config
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
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

# psycopg (the job queue's driver) cannot use Windows' default Proactor loop; asyncpg and httpx work on either.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # pyright: ignore[reportDeprecated]

from seedoc.config import get_settings  # noqa: E402
from seedoc.db import engine as db_engine  # noqa: E402
from seedoc.jobs.app import close_job_app, open_job_app  # noqa: E402
from seedoc.jobs.worker import QUEUES  # noqa: E402
from seedoc.mail import send as mail_send  # noqa: E402
from seedoc.main import create_app  # noqa: E402
from seedoc.models.tenants import MemberRole, Tenant, TenantMember, TenantStatus  # noqa: E402
from seedoc.models.users import User, UserSession  # noqa: E402
from seedoc.security.rate_limit import reset_rate_limits  # noqa: E402
from seedoc.security.sessions import SESSION_COOKIE  # noqa: E402
from seedoc.security.tokens import hash_token, new_token  # noqa: E402
from seedoc.security.totp import encrypt_totp_secret, new_totp_secret  # noqa: E402

ROLES_SQL = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init" / "01-roles.sql"
POSTGRES_IMAGE = "pgvector/pgvector:pg16"
S3_IMAGE = "rustfs/rustfs:latest"  # same image as infra/docker-compose.yml


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


@pytest.fixture(scope="session")
def s3() -> Iterator[str]:
    """RustFS (S3 API, the same server as `make up`) with an empty bucket; points the settings at it for the session.
    Yields the endpoint URL."""
    if not _docker_available():
        pytest.skip("Docker is not running; storage tests need testcontainers")

    from testcontainers.core.container import DockerContainer

    from seedoc.storage.s3 import get_s3_client

    container = (
        DockerContainer(S3_IMAGE)
        .with_env("RUSTFS_ACCESS_KEY", _TEST_ENV["S3_ACCESS_KEY"])
        .with_env("RUSTFS_SECRET_KEY", _TEST_ENV["S3_SECRET_KEY"])
        .with_env("RUSTFS_ADDRESS", ":9000")
        .with_exposed_ports(9000)
    )
    with container:
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        previous = os.environ["S3_ENDPOINT"]
        os.environ["S3_ENDPOINT"] = endpoint
        _reset_caches()
        get_s3_client.cache_clear()

        client = get_s3_client()
        for _ in range(60):  # the S3 port opens a moment after the container starts
            try:
                client.create_bucket(Bucket=_TEST_ENV["S3_BUCKET"])
                break
            except Exception:  # connection refused while RustFS is still starting
                time.sleep(0.5)
        else:
            pytest.fail("RustFS did not start within 30 s")

        yield endpoint
        os.environ["S3_ENDPOINT"] = previous
        _reset_caches()
        get_s3_client.cache_clear()


@pytest.fixture(scope="session", autouse=True)
async def job_app_pool() -> AsyncIterator[None]:
    """The API opens the job queue's pool on its first `defer`; close it once at the end (one loop per session)."""
    yield
    await close_job_app()


@pytest.fixture(autouse=True)
def reset_login_throttle() -> Iterator[None]:
    """The login throttle is process memory; without this, failures in one test would lock out the next."""
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture(autouse=True)
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[EmailMessage]:
    """Mails "sent" in this test, instead of SMTP. Mail goes through the `send_email` job: `await run_jobs()` first."""
    sent: list[EmailMessage] = []
    monkeypatch.setattr(mail_send, "_send_smtp", sent.append)
    return sent


def get_mail_link(message: EmailMessage, path: str) -> str:
    """The token of the first `APP_URL{path}<token>` link in the plain-text body, e.g. `path="/invite/"`."""
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    text: str = body.get_content()
    match = re.search(re.escape(get_settings().app_url + path) + r"(\S+)", text)
    assert match is not None, f"no {path} link in the mail"
    return match.group(1)


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


class RunJobs(Protocol):
    async def __call__(self) -> None: ...


@pytest.fixture
async def run_jobs(admin_db: AsyncSession) -> RunJobs:
    """Empties the job queue now (jobs of earlier tests must not run here); `await run_jobs()` then runs every job
    queued since, once, the way the worker does (as `seedoc_admin`, all queues). The API's pool is reopened on its
    next `defer`."""
    await admin_db.execute(text("delete from procrastinate_jobs"))
    await admin_db.commit()

    async def run() -> None:
        await close_job_app()
        app = await open_job_app(get_settings().database_admin_url)
        try:
            await app.run_worker_async(queues=QUEUES, wait=False, install_signal_handlers=False)
        finally:
            await close_job_app()

    return run


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
    async def __call__(self, role: MemberRole, tenant: Tenant | None = None) -> MemberClient: ...


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

    `await client_as(role, tenant=other.tenant)` adds the fresh member to an existing tenant instead, e.g. an editor
    next to an owner to test a 403 on the owner's data.

    The session row is created with `security.tokens` (the same hashing the API uses) and the client sends the
    `Origin` header the CSRF check expects. All clients are closed after the test.
    """
    clients: list[AsyncClient] = []
    app = create_app()
    origin = get_settings().app_url

    async def factory(role: MemberRole, tenant: Tenant | None = None) -> MemberClient:
        tenant = tenant or await make_tenant()
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
