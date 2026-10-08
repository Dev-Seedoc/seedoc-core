"""Demo data for local development and staging (ROADMAP M0-A10).

    make seed                      # create what is missing; prints passwords of newly created users once
    make seed ARGS=--reset-passwords   # give every demo user a new password and print them

Creates one demo tenant with an owner, an admin and an editor, plus a staff user. The staff user gets TOTP set up
(otpauth URI printed once) when `TOTP_ENCRYPTION_KEY` is configured. Idempotent: running it again creates nothing
that already exists and never changes an existing password or TOTP secret (`--reset-passwords` renews passwords only).
Refuses to run in production. Uses the admin engine (`seedoc_admin`, BYPASSRLS), like other jobs.
"""

import argparse
import asyncio
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

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
    print(f"Log in: POST {settings.app_url}/api/v1/auth/login  (login screen arrives with M0-B5)\n")


async def _main(reset_passwords: bool) -> None:
    try:
        async with get_admin_sessionmaker()() as db:
            result = await seed_demo_data(db, reset_passwords=reset_passwords)
        _print_result(result)
    finally:
        await dispose_engines()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SeeDoc demo data (never in production).")
    parser.add_argument("--reset-passwords", action="store_true", help="give every demo user a new password")
    args = parser.parse_args()
    if get_settings().is_production:
        sys.exit("Refusing to seed demo data in production.")
    asyncio.run(_main(reset_passwords=args.reset_passwords))


if __name__ == "__main__":
    main()
