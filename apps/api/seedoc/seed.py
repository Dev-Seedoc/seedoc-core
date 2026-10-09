"""Demo data for local development and staging (ROADMAP M0-A10).

    make seed                      # create what is missing; prints passwords of newly created users once
    make seed ARGS=--reset-passwords   # give every demo user a new password and print them
    make seed ARGS=--e2e-staff     # staff user for Playwright from apps/web/e2e/.env (or --e2e-staff <file>)

Creates one demo tenant with an owner, an admin and an editor, plus a staff user. The staff user gets TOTP set up
(otpauth URI printed once) when `TOTP_ENCRYPTION_KEY` is configured. Idempotent: running it again creates nothing
that already exists and never changes an existing password or TOTP secret (`--reset-passwords` renews passwords only).

`--e2e-staff` does only one thing: create or update the staff user named by `E2E_STAFF_EMAIL` with exactly the
password and TOTP secret from the file (NAMING §10, test only), so Playwright can log in. Nothing is printed.

Refuses to run in production. Uses the admin engine (`seedoc_admin`, BYPASSRLS), like other jobs.
"""

import argparse
import asyncio
import base64
import binascii
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.db.engine import dispose_engines, get_admin_sessionmaker
from seedoc.models.tenants import MemberRole, Tenant, TenantMember, TenantStatus
from seedoc.models.users import User
from seedoc.security.passwords import hash_password
from seedoc.security.totp import encrypt_totp_secret, get_totp_uri, new_totp_secret

DEMO_TENANT_NAME = "Demo Maschinenbau GmbH"
DEMO_TENANT_SLUG = "demo"
DEMO_PASSWORD_BYTES = 12  # token_urlsafe(12) → 16 characters, above the 12-character minimum
E2E_ENV_FILE = Path(__file__).resolve().parents[2] / "web" / "e2e" / ".env"
E2E_STAFF_FULL_NAME = "E2E Staff"
PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH = 12, 128  # BUSINESS_RULES §2


@dataclass(frozen=True)
class DemoUser:
    label: str
    email: str
    full_name: str
    role: MemberRole | None  # None = not a tenant member
    is_staff: bool = False


DEMO_USERS = (
    DemoUser("owner", "owner@demo.example.com", "Olivia Owner", MemberRole.OWNER),
    DemoUser("admin", "admin@demo.example.com", "Anton Admin", MemberRole.ADMIN),
    DemoUser("editor", "editor@demo.example.com", "Emma Editor", MemberRole.EDITOR),
    DemoUser("staff", "staff@seedoc.example.com", "Stefan Staff", None, is_staff=True),
)


@dataclass(frozen=True)
class SeededUser:
    label: str
    email: str
    password: str | None  # set only when created or reset in this run
    totp_uri: str | None = None  # set only when TOTP was set up in this run


@dataclass(frozen=True)
class SeedResult:
    tenant: Tenant
    tenant_created: bool
    users: list[SeededUser]


async def seed_demo_data(db: AsyncSession, reset_passwords: bool = False) -> SeedResult:
    """Create the demo tenant and users if missing. `db` must be an admin-engine session."""
    async with db.begin():
        tenant = await db.scalar(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
        tenant_created = tenant is None
        if tenant is None:
            tenant = Tenant(name=DEMO_TENANT_NAME, slug=DEMO_TENANT_SLUG, status=TenantStatus.ACTIVE)
            db.add(tenant)
            await db.flush()

        seeded: list[SeededUser] = []
        for demo in DEMO_USERS:
            user = await db.scalar(select(User).where(User.email == demo.email))
            password: str | None = None
            if user is None:
                password = secrets.token_urlsafe(DEMO_PASSWORD_BYTES)
                user = User(
                    email=demo.email,
                    full_name=demo.full_name,
                    is_staff=demo.is_staff,
                    password_hash=hash_password(password),
                )
                db.add(user)
                await db.flush()
            elif reset_passwords:
                password = secrets.token_urlsafe(DEMO_PASSWORD_BYTES)
                user.password_hash = hash_password(password)

            if demo.role is not None and await db.get(TenantMember, (tenant.id, user.id)) is None:
                db.add(TenantMember(tenant_id=tenant.id, user_id=user.id, role=demo.role))

            totp_uri: str | None = None
            if demo.is_staff and user.totp_enabled_at is None and get_settings().totp_encryption_key:
                secret = new_totp_secret()
                user.totp_secret_enc = encrypt_totp_secret(secret)
                user.totp_enabled_at = datetime.now(UTC)
                totp_uri = get_totp_uri(secret, demo.email)
            seeded.append(SeededUser(label=demo.label, email=demo.email, password=password, totp_uri=totp_uri))

    return SeedResult(tenant=tenant, tenant_created=tenant_created, users=seeded)


@dataclass(frozen=True)
class E2eStaff:
    email: str
    password: str
    totp_secret: str


def read_e2e_staff(path: Path) -> E2eStaff:
    """Read and check `E2E_STAFF_*` from a `KEY=value` file. Errors name the variable, never its value."""
    if not path.is_file():
        raise ValueError(f"{path} not found (copy apps/web/e2e/.env.example and fill it in)")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("\"'")

    missing = [key for key in ("E2E_STAFF_EMAIL", "E2E_STAFF_PASSWORD", "E2E_STAFF_TOTP_SECRET") if not values.get(key)]
    if missing:
        raise ValueError(f"missing in {path}: {', '.join(missing)}")
    staff = E2eStaff(
        email=values["E2E_STAFF_EMAIL"].lower(),
        password=values["E2E_STAFF_PASSWORD"],
        totp_secret=values["E2E_STAFF_TOTP_SECRET"].replace(" ", "").upper(),
    )
    if "@" not in staff.email:
        raise ValueError("E2E_STAFF_EMAIL is not an e-mail address")
    if not PASSWORD_MIN_LENGTH <= len(staff.password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(f"E2E_STAFF_PASSWORD must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters")
    try:
        base64.b32decode(staff.totp_secret + "=" * (-len(staff.totp_secret) % 8))
    except binascii.Error:
        raise ValueError("E2E_STAFF_TOTP_SECRET must be base32 (A-Z, 2-7), e.g. from pyotp.random_base32()") from None
    return staff


async def set_e2e_staff(db: AsyncSession, staff: E2eStaff) -> None:
    """Create or update the Playwright staff user with exactly these credentials. `db`: admin-engine session."""
    if not get_settings().totp_encryption_key:
        raise ValueError("TOTP_ENCRYPTION_KEY is empty; set it in .env first")
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == staff.email))
        if user is None:
            user = User(email=staff.email, full_name=E2E_STAFF_FULL_NAME, is_staff=True)
            db.add(user)
        elif not user.is_staff:
            # Never turn a manufacturer's account into staff by accident.
            raise ValueError("E2E_STAFF_EMAIL belongs to a user who is not staff; choose another address")
        user.password_hash = hash_password(staff.password)
        user.totp_secret_enc = encrypt_totp_secret(staff.totp_secret)
        user.totp_enabled_at = datetime.now(UTC)


def _print_result(result: SeedResult) -> None:
    settings = get_settings()
    state = "created" if result.tenant_created else "already there"
    print(f"\nTenant: {result.tenant.name} (slug '{result.tenant.slug}', id {result.tenant.id}) — {state}\n")
    print(f"  {'user':<8} {'e-mail':<28} password")
    for user in result.users:
        shown = user.password if user.password is not None else "(unchanged — use --reset-passwords to get a new one)"
        print(f"  {user.label:<8} {user.email:<28} {shown}")
    for user in result.users:
        if user.totp_uri:
            print(f"\n  TOTP for {user.email} (add it to an authenticator app):\n  {user.totp_uri}")
    if not settings.totp_encryption_key:
        print("\n  TOTP_ENCRYPTION_KEY is empty, so the staff user has no TOTP yet. Set it in .env and run again.")
    if any(user.password or user.totp_uri for user in result.users):
        print("\nSecrets are shown only now. Store them in your password manager.")
    print(f"Log in: {settings.app_url}/login\n")


async def _main(reset_passwords: bool) -> None:
    try:
        async with get_admin_sessionmaker()() as db:
            result = await seed_demo_data(db, reset_passwords=reset_passwords)
        _print_result(result)
    finally:
        await dispose_engines()


async def _main_e2e_staff(staff: E2eStaff) -> None:
    try:
        async with get_admin_sessionmaker()() as db:
            await set_e2e_staff(db, staff)
        print(f"E2E staff user ready: {staff.email} (password and TOTP secret from the e2e .env file)")
    finally:
        await dispose_engines()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SeeDoc demo data (never in production).")
    parser.add_argument("--reset-passwords", action="store_true", help="give every demo user a new password")
    parser.add_argument(
        "--e2e-staff",
        nargs="?",
        const=str(E2E_ENV_FILE),
        metavar="FILE",
        help="only create/update the Playwright staff user from FILE (default apps/web/e2e/.env)",
    )
    args = parser.parse_args()
    if get_settings().is_production:
        sys.exit("Refusing to seed demo data in production.")
    if args.e2e_staff is not None:
        try:
            staff = read_e2e_staff(Path(args.e2e_staff))
            asyncio.run(_main_e2e_staff(staff))
        except ValueError as exc:
            sys.exit(f"--e2e-staff: {exc}")
        return
    asyncio.run(_main(reset_passwords=args.reset_passwords))


if __name__ == "__main__":
    main()
