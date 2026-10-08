"""API tests for /api/v1/auth/totp/* (M0-A8, ARCHITECTURE §8)."""

from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.tenants import MemberRole
from seedoc.models.users import User, UserSession
from seedoc.security.tokens import hash_token
from tests.conftest import ClientAs, ClientStaff

pytestmark = pytest.mark.usefixtures("postgres")


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def test_setup_totp_requires_session(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/totp/setup")

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


async def test_setup_totp_is_staff_only(client_as: ClientAs) -> None:
    member = await client_as(MemberRole.OWNER)

    response = await member.http.post("/api/v1/auth/totp/setup")

    assert response.status_code == 403
    assert _error_code(response) == "forbidden"


async def test_enrolment_setup_then_verify(admin_db: AsyncSession, client_staff: ClientStaff) -> None:
    staff = await client_staff(mfa_verified=False, totp_enabled=False)

    setup = await staff.http.post("/api/v1/auth/totp/setup")

    assert setup.status_code == 200
    otpauth_uri: str = setup.json()["otpauth_uri"]
    uri = urlparse(otpauth_uri)
    assert uri.scheme == "otpauth"
    assert staff.user.email in uri.path
    secret = parse_qs(uri.query)["secret"][0]
    stored = await admin_db.scalar(select(User.totp_secret_enc).where(User.id == staff.user.id))
    assert stored is not None
    assert secret.encode() not in stored  # encrypted at rest

    verify = await staff.http.post("/api/v1/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()})

    assert verify.status_code == 204
    enabled_at = await admin_db.scalar(select(User.totp_enabled_at).where(User.id == staff.user.id))
    assert enabled_at is not None
    session_mfa = await admin_db.scalar(
        select(UserSession.mfa_verified_at).where(UserSession.token_hash == hash_token(staff.session_token))
    )
    assert session_mfa is not None
    me = await staff.http.get("/api/v1/auth/me")
    assert me.json()["mfa_verified"] is True
    assert (await staff.http.get("/api/v1/staff/tenants")).status_code == 200


async def test_setup_totp_refused_once_enabled(client_staff: ClientStaff) -> None:
    staff = await client_staff()

    response = await staff.http.post("/api/v1/auth/totp/setup")

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


async def test_verify_totp_wrong_code(client_staff: ClientStaff) -> None:
    staff = await client_staff(mfa_verified=False)
    current = pyotp.TOTP(staff.totp_secret).now()
    wrong = f"{(int(current) + 500_000) % 1_000_000:06d}"

    response = await staff.http.post("/api/v1/auth/totp/verify", json={"code": wrong})

    assert response.status_code == 401
    assert _error_code(response) == "invalid_credentials"
    assert (await staff.http.get("/api/v1/staff/tenants")).status_code == 401


async def test_verify_totp_without_enrolment_is_conflict(client_staff: ClientStaff) -> None:
    staff = await client_staff(mfa_verified=False, totp_enabled=False)

    response = await staff.http.post("/api/v1/auth/totp/verify", json={"code": "123456"})

    assert response.status_code == 409


async def test_verify_totp_throttled_after_10_wrong_codes(client_staff: ClientStaff) -> None:
    staff = await client_staff(mfa_verified=False)
    current = pyotp.TOTP(staff.totp_secret).now()
    wrong = f"{(int(current) + 500_000) % 1_000_000:06d}"
    for _ in range(10):
        assert (await staff.http.post("/api/v1/auth/totp/verify", json={"code": wrong})).status_code == 401

    blocked = await staff.http.post("/api/v1/auth/totp/verify", json={"code": current})

    assert blocked.status_code == 429
    assert _error_code(blocked) == "rate_limited"


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef"])
async def test_verify_totp_code_format(client_staff: ClientStaff, code: str) -> None:
    staff = await client_staff(mfa_verified=False)

    response = await staff.http.post("/api/v1/auth/totp/verify", json={"code": code})

    assert response.status_code == 422
