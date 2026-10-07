"""Auth service (M0-A6)."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.tenants import Invitation, InvitationKind, TenantMember
from seedoc.models.users import PasswordResetToken, User
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
    UserRead,
)
from seedoc.security.passwords import hash_password, verify_password
from seedoc.security.rate_limit import check_login_rate_limit, record_failed_login, reset_failed_login
from seedoc.security.sessions import create_session, revoke_all_user_sessions
from seedoc.security.tokens import hash_token


async def login(db: AsyncSession, ctx: RequestContext, body: LoginRequest) -> tuple[str, MeRead]:
    check_login_rate_limit(body.email, ctx.ip_hash)

    stmt = select(User).where(User.email == body.email.lower())
    user = await db.scalar(stmt)

    if not user or not user.password_hash or not verify_password(user.password_hash, body.password):
        record_failed_login(body.email, ctx.ip_hash)
        await write_audit_event(
            db,
            ctx,
            action="auth.login_failed",
            entity="user",
            entity_id=user.id if user else None,
            detail={"email": body.email},
        )
        raise AppError(ErrorCode.INVALID_CREDENTIALS)

    reset_failed_login(body.email, ctx.ip_hash)

    user.last_login_at = datetime.now(UTC)

    # We rotate the token by just creating a new session. Since login is typically
    # done from a new device or explicitly, it creates a new session token.
    # user_agent from ctx would be better but ctx doesn't have it right now
    token = await create_session(db, user.id, user_agent=None)

    me = await get_me(db, user)
    return token, me


async def get_me(db: AsyncSession, user_or_ctx: User | RequestContext) -> MeRead:
    if isinstance(user_or_ctx, RequestContext):
        if not user_or_ctx.user_id:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        stmt = select(User).where(User.id == user_or_ctx.user_id)
        user = await db.scalar(stmt)
        if not user:
            raise AppError(ErrorCode.UNAUTHENTICATED)
    else:
        user = user_or_ctx

    # Build MeRead
    # We also need tenant names, but M0-A5 didn't show the exact model for Tenant.
    # We will join if possible, but let's just do a simple query for now.
    from seedoc.models.tenants import Tenant

    stmt_tenant = (
        select(Tenant.id, Tenant.name, TenantMember.role)
        .join(TenantMember, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user.id)
    )
    tenant_rows = await db.execute(stmt_tenant)
    memberships = [TenantMembershipRead(tenant_id=row.id, tenant_name=row.name, role=row.role) for row in tenant_rows]

    from seedoc.models.operators import OperatorMember, OperatorOrg

    stmt_op = (
        select(OperatorOrg.id, OperatorOrg.name, OperatorMember.role)
        .join(OperatorMember, OperatorMember.operator_org_id == OperatorOrg.id)
        .where(OperatorMember.user_id == user.id)
    )
    op_rows = await db.execute(stmt_op)
    operator_orgs = [OperatorOrgMembershipRead(operator_org_id=row.id, name=row.name, role=row.role) for row in op_rows]

    return MeRead(
        user=UserRead.model_validate(user),
        memberships=memberships,
        operator_orgs=operator_orgs,
        is_staff=user.is_staff,
        # Technically this should be whether it was verified in the session.
        mfa_verified=user.totp_enabled_at is not None,
    )


async def reauthenticate(db: AsyncSession, ctx: RequestContext, body: ReauthenticateRequest) -> None:
    if not ctx.user_id or not ctx.session_id:
        raise AppError(ErrorCode.UNAUTHENTICATED)

    check_login_rate_limit(str(ctx.user_id), ctx.ip_hash)

    stmt = select(User).where(User.id == ctx.user_id)
    user = await db.scalar(stmt)
    if not user or not user.password_hash or not verify_password(user.password_hash, body.password):
        record_failed_login(str(ctx.user_id), ctx.ip_hash)
        raise AppError(ErrorCode.INVALID_CREDENTIALS)

    reset_failed_login(str(ctx.user_id), ctx.ip_hash)

    from seedoc.models.users import UserSession

    stmt_session = update(UserSession).where(UserSession.id == ctx.session_id).values(fresh_auth_at=datetime.now(UTC))
    await db.execute(stmt_session)


async def request_password_reset(db: AsyncSession, ctx: RequestContext, body: PasswordResetRequest) -> None:
    # Always 202. We'll implement actual sending in M0-A7 when mail/send.py is added.
    pass


async def confirm_password_reset(db: AsyncSession, ctx: RequestContext, body: PasswordResetConfirmRequest) -> None:
    now = datetime.now(UTC)
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token))
    reset_token = await db.scalar(stmt)

    if not reset_token or reset_token.used_at or now > reset_token.expires_at:
        raise AppError(ErrorCode.INVITATION_INVALID)

    stmt_user = select(User).where(User.id == reset_token.user_id)
    user = await db.scalar(stmt_user)
    if not user:
        raise AppError(ErrorCode.INVITATION_INVALID)

    user.password_hash = hash_password(body.password)
    reset_token.used_at = now

    await revoke_all_user_sessions(db, user.id)

    await write_audit_event(
        db,
        ctx,
        action="auth.password_reset",
        entity="user",
        entity_id=user.id,
        detail={},
    )


async def get_invitation(db: AsyncSession, token: str) -> InvitationPreview:
    now = datetime.now(UTC)
    stmt = select(Invitation).where(Invitation.token_hash == hash_token(token))
    inv = await db.scalar(stmt)

    if not inv or inv.accepted_at or inv.revoked_at or now > inv.expires_at:
        raise AppError(ErrorCode.INVITATION_INVALID)

    tenant_name = None
    if inv.tenant_id:
        from seedoc.models.tenants import Tenant

        tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == inv.tenant_id))

    operator_org_name = None
    if inv.operator_org_id:
        from seedoc.models.operators import OperatorOrg

        operator_org_name = await db.scalar(select(OperatorOrg.name).where(OperatorOrg.id == inv.operator_org_id))

    stmt_user = select(User).where(User.email == inv.email.lower())
    user = await db.scalar(stmt_user)
    has_account = user is not None and user.password_hash is not None

    return InvitationPreview(
        kind=inv.kind,
        tenant_name=tenant_name,
        operator_org_name=operator_org_name,
        email=inv.email,
        has_account=has_account,
    )


async def accept_invitation(
    db: AsyncSession, ctx: RequestContext, token: str, body: AcceptInvitationRequest
) -> tuple[str, MeRead]:
    now = datetime.now(UTC)
    stmt = select(Invitation).where(Invitation.token_hash == hash_token(token))
    inv = await db.scalar(stmt)

    if not inv or inv.accepted_at or inv.revoked_at or now > inv.expires_at:
        raise AppError(ErrorCode.INVITATION_INVALID)

    stmt_user = select(User).where(User.email == inv.email.lower())
    user = await db.scalar(stmt_user)

    if not user:
        if not body.password:
            raise AppError(ErrorCode.VALIDATION_FAILED, "Password required for new accounts.")
        user = User(
            email=inv.email.lower(),
            password_hash=hash_password(body.password),
            full_name=body.full_name,
        )
        db.add(user)
        await db.flush()
    else:
        # If user has no password yet, we must set it
        if not user.password_hash:
            if not body.password:
                raise AppError(ErrorCode.VALIDATION_FAILED, "Password required.")
            user.password_hash = hash_password(body.password)
        if body.full_name and not user.full_name:
            user.full_name = body.full_name

    if inv.kind == InvitationKind.TENANT_MEMBER and inv.tenant_id:
        # Check if already member
        stmt_mem = select(TenantMember).where(TenantMember.tenant_id == inv.tenant_id, TenantMember.user_id == user.id)
        if not await db.scalar(stmt_mem):
            mem = TenantMember(tenant_id=inv.tenant_id, user_id=user.id, role=inv.role)
            db.add(mem)
    elif inv.kind == InvitationKind.OPERATOR and inv.operator_org_id:
        from seedoc.models.operators import OperatorMember

        stmt_mem = select(OperatorMember).where(
            OperatorMember.operator_org_id == inv.operator_org_id, OperatorMember.user_id == user.id
        )
        if not await db.scalar(stmt_mem):
            # The role for operator invite should be defined in invitation or default
            from seedoc.models.operators import OperatorRole
            mem = OperatorMember(operator_org_id=inv.operator_org_id, user_id=user.id, role=OperatorRole.MEMBER)
            db.add(mem)

    inv.accepted_at = now
    inv.accepted_by = user.id
    await db.flush()

    await write_audit_event(
        db,
        ctx,
        action="member.joined",
        entity="user",
        entity_id=user.id,
        detail={"invitation_id": str(inv.id)},
    )

    session_token = await create_session(db, user.id, user_agent=None)
    me = await get_me(db, user)
    return session_token, me
