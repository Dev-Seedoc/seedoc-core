"""`make seed` (M0-A10): idempotent demo data whose printed credentials really work; `--e2e-staff` for Playwright."""

from pathlib import Path
from uuid import uuid4

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models.tenants import Tenant
from seedoc.security.sessions import SESSION_COOKIE
from seedoc.seed import (
    DEMO_TENANT_SLUG,
    DEMO_USERS,
    E2eStaff,
    SeedResult,
    read_e2e_staff,
    seed_demo_data,
    set_e2e_staff,
)
from tests.conftest import MakeUser

pytestmark = pytest.mark.usefixtures("postgres")

E2E_PASSWORD = "e2e-Password-123"
OTHER_E2E_PASSWORD = "e2e-Password-456"


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


# ─────────────────────────── --e2e-staff ───────────────────────────


def _e2e_file(tmp_path: Path, **values: str) -> Path:
    path = tmp_path / ".env"
    path.write_text("# Playwright\n" + "".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    return path


async def _set_e2e_staff(staff: E2eStaff) -> None:
    async with get_admin_sessionmaker()() as db:
        await set_e2e_staff(db, staff)


async def _login_with_totp(client: AsyncClient, email: str, password: str, totp_secret: str) -> int:
    """Log in, verify TOTP, then call a staff route; returns that route's status code."""
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    # The session cookie is Secure, so the test client does not send it back over http: pass it explicitly.
    headers = {"Cookie": f"{SESSION_COOKIE}={login.cookies[SESSION_COOKIE]}", "Origin": get_settings().app_url}
    verify = await client.post(
        "/api/v1/auth/totp/verify", json={"code": pyotp.TOTP(totp_secret).now()}, headers=headers
    )
    assert verify.status_code == 204
    return (await client.get("/api/v1/staff/tenants", headers=headers)).status_code


def test_read_e2e_staff_normalizes_values(tmp_path: Path) -> None:
    secret = pyotp.random_base32()
    path = _e2e_file(
        tmp_path,
        E2E_BASE_URL="http://localhost:5173",
        E2E_STAFF_EMAIL=" E2E@Example.com",
        E2E_STAFF_PASSWORD=f'"{E2E_PASSWORD}"',
        E2E_STAFF_TOTP_SECRET=secret.lower(),
    )

    assert read_e2e_staff(path) == E2eStaff(email="e2e@example.com", password=E2E_PASSWORD, totp_secret=secret)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"E2E_STAFF_EMAIL": "e2e@example.com", "E2E_STAFF_PASSWORD": E2E_PASSWORD}, "E2E_STAFF_TOTP_SECRET"),
        (
            {"E2E_STAFF_EMAIL": "no-at-sign", "E2E_STAFF_PASSWORD": E2E_PASSWORD, "E2E_STAFF_TOTP_SECRET": "JBSWY3DP"},
            "e-mail",
        ),
        (
            {"E2E_STAFF_EMAIL": "e2e@example.com", "E2E_STAFF_PASSWORD": "short", "E2E_STAFF_TOTP_SECRET": "JBSWY3DP"},
            "12-128",
        ),
        (
            {
                "E2E_STAFF_EMAIL": "e2e@example.com",
                "E2E_STAFF_PASSWORD": E2E_PASSWORD,
                "E2E_STAFF_TOTP_SECRET": "not!b32",
            },
            "base32",
        ),
    ],
)
def test_read_e2e_staff_rejects_bad_files_without_echoing_values(
    tmp_path: Path, values: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message) as error:
        read_e2e_staff(_e2e_file(tmp_path, **values))

    assert E2E_PASSWORD not in str(error.value)


def test_read_e2e_staff_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        read_e2e_staff(tmp_path / "missing.env")


async def test_set_e2e_staff_creates_and_updates_a_working_staff_login(client: AsyncClient) -> None:
    email = f"e2e-{uuid4().hex[:8]}@example.com"
    first = E2eStaff(email=email, password=E2E_PASSWORD, totp_secret=pyotp.random_base32())
    second = E2eStaff(email=email, password=OTHER_E2E_PASSWORD, totp_secret=pyotp.random_base32())

    await _set_e2e_staff(first)
    assert await _login_with_totp(client, email, E2E_PASSWORD, first.totp_secret) == 200

    await _set_e2e_staff(second)  # running again replaces password and TOTP secret
    old = await client.post("/api/v1/auth/login", json={"email": email, "password": E2E_PASSWORD})
    assert old.status_code == 401
    assert await _login_with_totp(client, email, OTHER_E2E_PASSWORD, second.totp_secret) == 200


async def test_set_e2e_staff_refuses_a_non_staff_user(make_user: MakeUser) -> None:
    member = await make_user()

    with pytest.raises(ValueError, match="not staff"):
        await _set_e2e_staff(E2eStaff(email=member.email, password=E2E_PASSWORD, totp_secret=pyotp.random_base32()))
