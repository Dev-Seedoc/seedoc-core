"""Mail jobs (ARCHITECTURE §11, queue `mail`). Thin: the link is made in services/mail.py, the send in mail/send.py."""

import asyncio
from uuid import UUID

import procrastinate
import structlog

from seedoc.config import get_settings
from seedoc.jobs.app import app, open_job_app
from seedoc.mail.send import MailTemplate, deliver_email
from seedoc.services import mail as mail_service

log = structlog.get_logger()

MAIL_QUEUE = "mail"
SEND_EMAIL_RETRIES = 5  # after the first try; waits 4 s, 16 s, 64 s, ~4 min, ~17 min


@app.task(
    name="send_email",
    queue=MAIL_QUEUE,
    retry=procrastinate.RetryStrategy(max_attempts=SEND_EMAIL_RETRIES, exponential_wait=4),
)
async def send_email(template: str, target_id: str) -> None:
    """`target_id` = the user (password reset) or the invitation. Never any address or token in the arguments."""
    mail_template = MailTemplate(template)
    prepared = await mail_service.prepare_mail(mail_template, UUID(target_id))
    if prepared is not None:
        await asyncio.to_thread(deliver_email, mail_template, prepared.to, prepared.context)


async def defer_send_email(template: MailTemplate, target_id: UUID) -> None:
    """Queue the mail after the caller's transaction committed. Never raises: a queue problem is logged
    (`job_defer_failed`) and the request still succeeds, as an SMTP problem would."""
    try:
        await open_job_app(get_settings().database_url)
        await send_email.defer_async(template=template.value, target_id=str(target_id))
    except Exception as exc:
        log.error("job_defer_failed", job="send_email", template=template.value, error=type(exc).__name__)
