"""Link mails (password reset, invitations) for the `send_email` job (jobs/mail.py).

A request queues only the template and an id. The job creates the one-time token here, stores its hash and builds
the link right before sending, so a raw token never sits in the job queue (job arguments are ids only). Runs in the
worker as `seedoc_admin`; the token is committed before SMTP is tried.

On a retry the token is created again: an invitation keeps only the newest hash (older links stop working), a
password reset gets one more short-lived token row.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.mail.send import MailTemplate, get_app_link
from seedoc.models.tenants import Invitation, Tenant
from seedoc.models.users import PasswordResetToken, User
from seedoc.security.tokens import hash_token, new_token

log = structlog.get_logger()

PASSWORD_RESET_TTL = timedelta(hours=1)


@dataclass(frozen=True)
class PreparedMail:
    to: str
    context: dict[str, str]


async def prepare_mail(template: MailTemplate, target_id: UUID) -> PreparedMail | None:
    """Recipient and template values with a fresh link, or `None` when there is nothing to send any more (user gone;
    invitation accepted, revoked or expired)."""
    async with get_admin_sessionmaker()() as db, db.begin():
        match template:
            case MailTemplate.PASSWORD_RESET:
                prepared = await _prepare_password_reset(db, target_id)
            case MailTemplate.INVITATION_TENANT_MEMBER:
                prepared = await _prepare_invitation(db, target_id)
    if prepared is None:
        log.info("mail_skipped", template=template.value, target_id=str(target_id))
    return prepared


async def _prepare_password_reset(db: AsyncSession, user_id: UUID) -> PreparedMail | None:
    email = await db.scalar(select(User.email).where(User.id == user_id))
    if email is None:
        return None
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user_id, token_hash=hash_token(token), expires_at=datetime.now(UTC) + PASSWORD_RESET_TTL
        )
    )
    return PreparedMail(to=email, context={"reset_url": get_app_link(f"/reset-password/{token}")})


async def _prepare_invitation(db: AsyncSession, invitation_id: UUID) -> PreparedMail | None:
    row = (
        await db.execute(
            select(Invitation, Tenant.name)
            .join(Tenant, Tenant.id == Invitation.tenant_id)
            .where(Invitation.id == invitation_id)
            .with_for_update(of=Invitation)
        )
    ).one_or_none()
    if row is None:
        return None
    invitation, tenant_name = row
    if invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= datetime.now(UTC):
        return None
    token = new_token()
    invitation.token_hash = hash_token(token)
    return PreparedMail(
        to=invitation.email,
        context={"tenant_name": tenant_name, "invitation_url": get_app_link(f"/invite/{token}")},
    )
