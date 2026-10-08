"""Auth service (API.md §2, BUSINESS_RULES §2). Each function owns its transaction."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import set_tenant
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.operators import OperatorMember, OperatorOrg, OperatorRole
from seedoc.models.tenants import Invitation, InvitationKind, MemberRole, Tenant, TenantMember
from seedoc.models.users import PasswordResetToken, User, UserSession
from seedoc.schemas.auth import (
    AcceptInvitationRequest,
    InvitationPreview,
    LoginRequest,
    MeRead,
    OperatorOrgMembershipRead,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ReauthenticateRequest,
    TenantMembershipRead,
    TotpSetupRead,
    UserRead,
    VerifyTotpRequest,
)
from seedoc.security.passwords import hash_password, verify_password_or_dummy
from seedoc.security.rate_limit import check_login_rate_limit, record_failed_login, reset_failed_login
from seedoc.security.sessions import create_session, revoke_all_user_sessions, revoke_session
from seedoc.security.tokens import hash_token, new_token
from seedoc.security.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_totp_uri,
    new_totp_secret,
    verify_totp_code,
)

PASSWORD_RESET_TTL = timedelta(hours=1)


class _WrongPasswordError(Exception):
    """Internal: lets a transaction roll back before the failure is counted and reported."""

    def __init__(self, subject: str) -> None:
        super().__init__(subject)
        self.subject = subject


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def login(
    db: AsyncSession, ctx: RequestContext, body: LoginRequest, user_agent: str | None
) -> tuple[str, MeRead]:
    email = _normalize_email(body.email)
    check_login_rate_limit(email, ctx.ip_hash)

    result: tuple[str, MeRead] | None = None
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == email))
        if user is not None and verify_password_or_dummy(user.password_hash, body.password):
            if ctx.session_id is not None:  # rotate: a login always replaces the session the browser had
                await revoke_session(db, ctx.session_id)
            user.last_login_at = datetime.now(UTC)
            token = await create_session(db, user.id, user_agent)
            result = token, await _build_me(db, user, mfa_verified=False)
        else:
            if user is None:
                verify_password_or_dummy(None, body.password)  # same Argon2 cost as a known e-mail
            # Committed even though the request fails: the audit trail must keep failed logins.
            await write_audit_event(
                db, ctx, action="auth.login_failed", entity="user", entity_id=user.id if user else None
            )

    if result is None:
        record_failed_login(email, ctx.ip_hash)
        raise AppError(ErrorCode.INVALID_CREDENTIALS)
    reset_failed_login(email)
    return result


async def logout(db: AsyncSession, ctx: RequestContext) -> None:
    if ctx.session_id is None:
        return
    async with db.begin():
        await revoke_session(db, ctx.session_id)


async def get_me(db: AsyncSession, ctx: RequestContext) -> MeRead:
    if ctx.user_id is None or ctx.session_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    async with db.begin():
        user = await db.get(User, ctx.user_id)
        if user is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        mfa_verified_at = await db.scalar(select(UserSession.mfa_verified_at).where(UserSession.id == ctx.session_id))
        return await _build_me(db, user, mfa_verified=mfa_verified_at is not None)


async def reauthenticate(db: AsyncSession, ctx: RequestContext, body: ReauthenticateRequest) -> None:
    if ctx.user_id is None or ctx.session_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    subject = f"reauth:{ctx.user_id}"
    check_login_rate_limit(subject, ctx.ip_hash)

    try:
        async with db.begin():
            password_hash = await db.scalar(select(User.password_hash).where(User.id == ctx.user_id))
            if not verify_password_or_dummy(password_hash, body.password):
                raise _WrongPasswordError(subject)
            await db.execute(
                update(UserSession).where(UserSession.id == ctx.session_id).values(fresh_auth_at=datetime.now(UTC))
            )
    except _WrongPasswordError as wrong:
        record_failed_login(wrong.subject, ctx.ip_hash)
        raise AppError(ErrorCode.INVALID_CREDENTIALS) from None
    reset_failed_login(subject)


async def request_password_reset(db: AsyncSession, ctx: RequestContext, body: PasswordResetRequest) -> None:
    """Always succeeds (202), whether or not the e-mail has an account — no user enumeration."""
    async with db.begin():
        user_id = await db.scalar(select(User.id).where(User.email == _normalize_email(body.email)))
        if user_id is None:
            return
        token = new_token()
        db.add(
            PasswordResetToken(
                user_id=user_id, token_hash=hash_token(token), expires_at=datetime.now(UTC) + PASSWORD_RESET_TTL
            )
        )
        # TODO(M0-A7): send the `password_reset` mail with `token` (link /reset-password/{token}).


async def confirm_password_reset(db: AsyncSession, ctx: RequestContext, body: PasswordResetConfirmRequest) -> None:
    if not body.token.isascii():
        raise AppError(ErrorCode.INVITATION_INVALID)
    now = datetime.now(UTC)
    async with db.begin():
        reset_token = await db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token))
        )
        if reset_token is None or reset_token.used_at is not None or now >= reset_token.expires_at:
            raise AppError(ErrorCode.INVITATION_INVALID)
        user = await db.get(User, reset_token.user_id)
        if user is None:
            raise AppError(ErrorCode.INVITATION_INVALID)

        user.password_hash = hash_password(body.password)
        # Single use, and any other outstanding reset link of this user dies with it.
        await db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        await revoke_all_user_sessions(db, user.id)
        await write_audit_event(
            db, ctx, action="auth.password_reset", entity="user", entity_id=user.id, actor_id=user.id
        )


async def get_invitation(db: AsyncSession, token: str) -> InvitationPreview:
    async with db.begin():
        invitation = await _load_open_invitation(db, token)
        tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == invitation.tenant_id))
        operator_org_name = (
            await db.scalar(select(OperatorOrg.name).where(OperatorOrg.id == invitation.operator_org_id))
            if invitation.operator_org_id
            else None
        )
        password_hash = await db.scalar(select(User.password_hash).where(User.email == invitation.email))
        return InvitationPreview(
            kind=invitation.kind,
            tenant_name=tenant_name,
            operator_org_name=operator_org_name,
            email=invitation.email,
            has_account=password_hash is not None,
        )


async def accept_invitation(
    db: AsyncSession, ctx: RequestContext, token: str, body: AcceptInvitationRequest, user_agent: str | None
) -> tuple[str, MeRead]:
    """Join the tenant (or operator org) of the invitation and log in.

    - no account yet → `password` required, the user is created;
    - account without a password (invited earlier, never accepted) → `password` required and set;
    - account with a password → the caller must be logged in as that user **or** send the account's password.
      The invitation token alone never logs anyone into an existing account.
    """
    try:
        async with db.begin():
            invitation = await _load_open_invitation(db, token)
            email = _normalize_email(invitation.email)
            user = await db.scalar(select(User).where(User.email == email))

            if ctx.user_id is not None and (user is None or ctx.user_id != user.id):
                raise AppError(ErrorCode.FORBIDDEN, "logged in as a different user than the invitation is for")

            if user is None:
                user = User(email=email, password_hash=hash_password(_require_password(body)), full_name=body.full_name)
                db.add(user)
                await db.flush()
            elif user.password_hash is None:
                user.password_hash = hash_password(_require_password(body))
            elif ctx.user_id != user.id:
                check_login_rate_limit(email, ctx.ip_hash)
                if body.password is None or not verify_password_or_dummy(user.password_hash, body.password):
                    raise _WrongPasswordError(email)
            if body.full_name and not user.full_name:
                user.full_name = body.full_name

            await _add_membership(db, invitation, user.id)
            invitation.accepted_at = datetime.now(UTC)
            invitation.accepted_by = user.id
            await write_audit_event(
                db,
                ctx,
                action="member.joined",
                entity="invitation",
                entity_id=invitation.id,
                detail={"user_id": str(user.id), "kind": invitation.kind.value},
                tenant_id=invitation.tenant_id,
                actor_id=user.id,
            )

            if ctx.session_id is not None:
                await revoke_session(db, ctx.session_id)
            session_token = await create_session(db, user.id, user_agent)
            me = await _build_me(db, user, mfa_verified=False)
    except _WrongPasswordError as wrong:
        record_failed_login(wrong.subject, ctx.ip_hash)
        raise AppError(ErrorCode.INVALID_CREDENTIALS) from None
    return session_token, me


async def setup_totp(db: AsyncSession, ctx: RequestContext) -> TotpSetupRead:
    """Start TOTP enrolment for a staff user: store a new encrypted secret, return the `otpauth://` URI.

    Enrolment is only possible while TOTP is not yet active. Once `verify_totp` succeeded the secret can no longer be
    replaced through the API (a stolen password must not be enough to move the second factor to another phone).
    """
    user_id = _require_staff_session(ctx)
    async with db.begin():
        user = await db.get(User, user_id)
        if user is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        if user.totp_enabled_at is not None:
            raise AppError(ErrorCode.CONFLICT, "TOTP is already set up")
        secret = new_totp_secret()
        user.totp_secret_enc = encrypt_totp_secret(secret)
        return TotpSetupRead(otpauth_uri=get_totp_uri(secret, user.email))


async def verify_totp(db: AsyncSession, ctx: RequestContext, body: VerifyTotpRequest) -> None:
    """Check a TOTP code; on success the session counts as MFA-verified and enrolment (if pending) is complete."""
    user_id = _require_staff_session(ctx)
    subject = f"totp:{user_id}"
    check_login_rate_limit(subject, ctx.ip_hash)
    try:
        async with db.begin():
            user = await db.get(User, user_id)
            if user is None or user.totp_secret_enc is None:
                raise AppError(ErrorCode.CONFLICT, "TOTP is not set up")
            if not verify_totp_code(decrypt_totp_secret(user.totp_secret_enc), body.code):
                raise _WrongPasswordError(subject)
            now = datetime.now(UTC)
            if user.totp_enabled_at is None:
                user.totp_enabled_at = now
            await db.execute(update(UserSession).where(UserSession.id == ctx.session_id).values(mfa_verified_at=now))
    except _WrongPasswordError as wrong:
        record_failed_login(wrong.subject, ctx.ip_hash)
        raise AppError(ErrorCode.INVALID_CREDENTIALS) from None
    reset_failed_login(subject)


def _require_staff_session(ctx: RequestContext) -> UUID:
    if ctx.user_id is None or ctx.session_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if not ctx.is_staff:
        raise AppError(ErrorCode.FORBIDDEN)
    return ctx.user_id


def _require_password(body: AcceptInvitationRequest) -> str:
    if body.password is None:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            details={"fields": [{"loc": ["body", "password"], "type": "missing", "msg": "Field required"}]},
        )
    return body.password


async def _load_open_invitation(db: AsyncSession, token: str) -> Invitation:
    """Find the invitation for `token`, scope the transaction to its tenant, and check it is still open.

    `invitations` is under RLS and no tenant is known yet, so the SECURITY DEFINER `resolve_invitation()` returns
    only the ids; the row itself is then read under RLS like any other tenant data.
    """
    if not token.isascii():
        raise AppError(ErrorCode.INVITATION_INVALID)
    row = (
        await db.execute(
            text("select invitation_id, tenant_id from resolve_invitation(:token_hash)"),
            {"token_hash": hash_token(token)},
        )
    ).one_or_none()
    if row is None:
        raise AppError(ErrorCode.INVITATION_INVALID)
    invitation_id: UUID = row.invitation_id
    tenant_id: UUID = row.tenant_id
    await set_tenant(db, tenant_id)

    invitation = await db.get(Invitation, invitation_id)
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or datetime.now(UTC) >= invitation.expires_at
    ):
        raise AppError(ErrorCode.INVITATION_INVALID)
    return invitation


async def _add_membership(db: AsyncSession, invitation: Invitation, user_id: UUID) -> None:
    if invitation.kind is InvitationKind.TENANT_MEMBER:
        if invitation.role is None:  # excluded by ck_invitations_kind_fields
            raise AppError(ErrorCode.INVITATION_INVALID)
        existing = await db.get(TenantMember, (invitation.tenant_id, user_id))
        if existing is None:
            db.add(TenantMember(tenant_id=invitation.tenant_id, user_id=user_id, role=invitation.role))
        return

    if invitation.operator_org_id is None:  # excluded by ck_invitations_kind_fields
        raise AppError(ErrorCode.INVITATION_INVALID)
    if await db.get(OperatorMember, (invitation.operator_org_id, user_id)) is not None:
        return
    member_count = await db.scalar(
        select(func.count())
        .select_from(OperatorMember)
        .where(OperatorMember.operator_org_id == invitation.operator_org_id)
    )
    # BUSINESS_RULES §13: the first member of an operator org is its admin.
    role = OperatorRole.ADMIN if not member_count else OperatorRole.MEMBER
    db.add(OperatorMember(operator_org_id=invitation.operator_org_id, user_id=user_id, role=role))


async def _build_me(db: AsyncSession, user: User, mfa_verified: bool) -> MeRead:
    # member_tenants() is SECURITY DEFINER because tenant_members/tenants are under RLS.
    tenant_rows = await db.execute(
        text("select tenant_id, tenant_name, role from member_tenants(:user_id) order by tenant_name"),
        {"user_id": user.id},
    )
    memberships = [
        TenantMembershipRead(tenant_id=row.tenant_id, tenant_name=row.tenant_name, role=MemberRole(row.role))
        for row in tenant_rows
    ]
    org_rows = await db.execute(
        select(OperatorOrg.id, OperatorOrg.name, OperatorMember.role)
        .join(OperatorMember, OperatorMember.operator_org_id == OperatorOrg.id)
        .where(OperatorMember.user_id == user.id)
        .order_by(OperatorOrg.name)
    )
    operator_orgs = [
        OperatorOrgMembershipRead(operator_org_id=org_id, name=name, role=role) for org_id, name, role in org_rows
    ]
    return MeRead(
        user=UserRead.model_validate(user),
        memberships=memberships,
        operator_orgs=operator_orgs,
        is_staff=user.is_staff,
        mfa_verified=mfa_verified,
    )
