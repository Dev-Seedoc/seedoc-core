"""Mail through the `send_email` job (ARCHITECTURE §11): requests queue ids only; the job makes the link and sends."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.jobs.mail import defer_send_email
from seedoc.mail import send as mail_send
from seedoc.mail.send import MailTemplate
from seedoc.models.tenants import Invitation, InvitationKind, MemberRole
from seedoc.models.users import PasswordResetToken
from seedoc.security.tokens import hash_token, new_token
from tests.conftest import MakeTenant, MakeUser, RunJobs, get_mail_link

pytestmark = pytest.mark.usefixtures("postgres")


async def _queued(admin_db: AsyncSession) -> list[tuple[str, str, dict[str, str]]]:
    rows = await admin_db.execute(text("select task_name, queue_name, args from procrastinate_jobs order by id"))
    return [(row.task_name, row.queue_name, row.args) for row in rows]


async def _invitation(admin_db: AsyncSession, make_tenant: MakeTenant, **values: object) -> Invitation:
    tenant = await make_tenant(name="Alpha Maschinenbau")
    invitation = Invitation(
        tenant_id=tenant.id,
        kind=InvitationKind.TENANT_MEMBER,
        email=f"owner-{uuid4().hex[:8]}@example.com",
        role=MemberRole.OWNER,
        **{"token_hash": hash_token(new_token()), "expires_at": datetime.now(UTC) + timedelta(days=7), **values},
    )
    admin_db.add(invitation)
    await admin_db.commit()
    return invitation


async def test_password_reset_queues_only_the_user_id(
    admin_db: AsyncSession, make_user: MakeUser, client: AsyncClient, run_jobs: RunJobs, outbox: list[EmailMessage]
) -> None:
    user = await make_user()

    response = await client.post("/api/v1/auth/password-reset", json={"email": user.email})

    assert response.status_code == 202
    assert await _queued(admin_db) == [
        ("send_email", "mail", {"template": "password_reset", "target_id": str(user.id)})
    ]
    # No token exists until the job runs, so the queue never holds one.
    count = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    assert await admin_db.scalar(count) == 0

    await run_jobs()

    assert await admin_db.scalar(count) == 1
    assert [mail["To"] for mail in outbox] == [user.email]


async def test_unknown_email_queues_nothing(client: AsyncClient, admin_db: AsyncSession, run_jobs: RunJobs) -> None:
    response = await client.post("/api/v1/auth/password-reset", json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert await _queued(admin_db) == []


async def test_a_resent_invitation_replaces_the_earlier_link(
    admin_db: AsyncSession, make_tenant: MakeTenant, client: AsyncClient, run_jobs: RunJobs, outbox: list[EmailMessage]
) -> None:
    invitation = await _invitation(admin_db, make_tenant)

    await defer_send_email(MailTemplate.INVITATION_TENANT_MEMBER, invitation.id)
    await run_jobs()
    await defer_send_email(MailTemplate.INVITATION_TENANT_MEMBER, invitation.id)  # e.g. a retry after SMTP failed
    await run_jobs()

    first, second = (get_mail_link(mail, "/invite/") for mail in outbox)
    assert first != second
    assert (await client.get(f"/api/v1/auth/invitations/{first}")).status_code == 410
    preview = await client.get(f"/api/v1/auth/invitations/{second}")
    assert preview.status_code == 200
    assert preview.json()["tenant_name"] == "Alpha Maschinenbau"


@pytest.mark.parametrize(
    "values",
    [
        {"accepted_at": datetime.now(UTC)},
        {"revoked_at": datetime.now(UTC)},
        {"expires_at": datetime.now(UTC) - timedelta(minutes=1)},
    ],
    ids=["accepted", "revoked", "expired"],
)
async def test_a_finished_invitation_is_not_mailed(
    admin_db: AsyncSession,
    make_tenant: MakeTenant,
    run_jobs: RunJobs,
    outbox: list[EmailMessage],
    values: dict[str, object],
) -> None:
    invitation = await _invitation(admin_db, make_tenant, **values)
    token_hash = invitation.token_hash

    await defer_send_email(MailTemplate.INVITATION_TENANT_MEMBER, invitation.id)
    await run_jobs()

    assert outbox == []
    await admin_db.refresh(invitation)
    assert invitation.token_hash == token_hash


async def test_smtp_failure_keeps_the_job_for_a_retry(
    admin_db: AsyncSession, make_user: MakeUser, run_jobs: RunJobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_: EmailMessage) -> None:
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(mail_send, "_send_smtp", refuse)
    user = await make_user()

    await defer_send_email(MailTemplate.PASSWORD_RESET, user.id)
    await run_jobs()

    row = (await admin_db.execute(text("select status::text, attempts, scheduled_at from procrastinate_jobs"))).one()
    assert (row.status, row.attempts) == ("todo", 1)  # back in the queue
    assert row.scheduled_at > datetime.now(UTC)  # after the backoff wait
