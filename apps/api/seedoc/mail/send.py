"""Mail (ARCHITECTURE D20): render `templates/<name>.de.{txt,html}` and send over SMTP.

Template format: the first line of the `.txt` file is the subject, the rest is the plain-text body; the `.html` file
is the HTML body. Placeholders are `{{ name }}`; values are HTML-escaped in the HTML body. The leading `<!-- … -->`
comment of an HTML template documents it and is not sent.

Until the worker exists (M1-A6) `send_email` sends in a background task of the API process, so a response never
waits for SMTP (and `request_password_reset` takes the same time for known and unknown addresses). A failed send is
logged, not retried; M1-A6 moves delivery into the `send_email` job (5 retries) behind the same function.
"""

import asyncio
import html
import re
import smtplib
import ssl
from email.message import EmailMessage
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import structlog

from seedoc.config import SMTP_TLS_PORTS, get_settings

SMTP_TIMEOUT_SECONDS = 30

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_LANGUAGE = "de"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_DOC_COMMENT = re.compile(r"<!--.*?-->\s*", re.DOTALL)

log = structlog.get_logger()

# Running sends; kept so the tasks are not garbage-collected and can be awaited on shutdown.
_pending: set[asyncio.Task[None]] = set()


class MailTemplate(StrEnum):
    """Template names (NAMING §12)."""

    INVITATION_TENANT_MEMBER = "invitation_tenant_member"
    PASSWORD_RESET = "password_reset"  # noqa: S105 — a template name, not a password


def get_app_link(path: str) -> str:
    """Absolute link into the web app for a mail, e.g. `/invite/{token}` → `https://app.seedoc.cloud/invite/…`."""
    return get_settings().app_url.rstrip("/") + path


def build_email(template: MailTemplate, to: str, context: dict[str, str]) -> EmailMessage:
    """Render `template` for `to`; a placeholder without a value in `context` raises `KeyError`."""
    text_source, html_source = _get_template_sources(template)
    subject_line, _, text_body = text_source.partition("\n")

    message = EmailMessage()
    message["From"] = get_settings().mail_from
    message["To"] = to
    message["Subject"] = " ".join(_render(subject_line, context, escape=False).split())  # never a line break
    message.set_content(_render(text_body.lstrip("\n"), context, escape=False))
    message.add_alternative(_render(html_source, context, escape=True), subtype="html")
    return message


def send_email(template: MailTemplate, to: str, context: dict[str, str]) -> None:
    """Render now (errors surface in the request) and send in the background. Call after the transaction commits."""
    message = build_email(template, to, context)
    task = asyncio.get_running_loop().create_task(_deliver(template, message))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def send_pending_mail() -> None:
    """Wait until every mail queued on this event loop is sent (or has failed). Used on shutdown and in tests.

    Finished tasks are dropped here rather than trusted to `_pending.discard`: that callback runs on the task's own
    loop, and a task from a loop that has stopped (one test's loop, seen from the next) would otherwise stay in
    `_pending` forever and make this loop spin.
    """
    loop = asyncio.get_running_loop()
    while True:
        _pending.difference_update({task for task in _pending if task.done() or task.get_loop().is_closed()})
        waiting = [task for task in _pending if task.get_loop() is loop]
        if not waiting:
            return
        await asyncio.gather(*waiting)


@lru_cache
def _get_template_sources(template: MailTemplate) -> tuple[str, str]:
    text_source = (_TEMPLATE_DIR / f"{template.value}.{_LANGUAGE}.txt").read_text(encoding="utf-8")
    html_source = (_TEMPLATE_DIR / f"{template.value}.{_LANGUAGE}.html").read_text(encoding="utf-8")
    return text_source, _DOC_COMMENT.sub("", html_source, count=1)


def _render(source: str, context: dict[str, str], *, escape: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        value = context[match.group(1)]
        return html.escape(value) if escape else value

    return _PLACEHOLDER.sub(replace, source)


async def _deliver(template: MailTemplate, message: EmailMessage) -> None:
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (smtplib.SMTPException, OSError) as exc:
        # Only the error type: SMTP error texts can contain the recipient address.
        log.error("mail_send_failed", template=template.value, error=type(exc).__name__)
    else:
        log.info("mail_sent", template=template.value)


def _send_smtp(message: EmailMessage) -> None:
    settings = get_settings()
    host, port = settings.mail_smtp_host, settings.mail_smtp_port
    if port in SMTP_TLS_PORTS:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=SMTP_TIMEOUT_SECONDS, context=ssl.create_default_context()
        )
    else:  # Mailpit locally; config.py allows only the TLS port outside local
        smtp = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)
    with smtp:
        if settings.mail_smtp_user:
            smtp.login(settings.mail_smtp_user, settings.mail_api_key)
        smtp.send_message(message)
