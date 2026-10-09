"""Unit tests for mail rendering and SMTP delivery (M0-A7, ARCHITECTURE D20)."""

import ssl
from collections.abc import Iterator
from email.message import EmailMessage
from typing import ClassVar, Self

import pytest
import structlog

from seedoc.config import get_settings
from seedoc.mail import send as mail_send
from seedoc.mail.send import MailTemplate, build_email, get_app_link, send_email, send_pending_mail

# The autouse `outbox` fixture replaces `_send_smtp`; keep the real one for the SMTP tests.
_real_send_smtp = mail_send._send_smtp  # pyright: ignore[reportPrivateUsage]

INVITATION = {"tenant_name": "Alpha Maschinenbau", "invitation_url": "http://localhost:5173/invite/abc"}


def _part(message: EmailMessage, subtype: str) -> str:
    part = message.get_body(preferencelist=(subtype,))
    assert part is not None
    content: str = part.get_content()
    return content


class _FakeSmtp:
    created: ClassVar[list["_FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float, context: ssl.SSLContext | None = None) -> None:
        self.host, self.port, self.context = host, port, context
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        _FakeSmtp.created.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_FakeSmtp]]:
    _FakeSmtp.created = []
    monkeypatch.setattr(mail_send.smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(mail_send.smtplib, "SMTP_SSL", _FakeSmtp)
    yield _FakeSmtp
    get_settings.cache_clear()  # the tests below change MAIL_* env vars


def test_build_email_renders_subject_text_and_html() -> None:
    message = build_email(MailTemplate.INVITATION_TENANT_MEMBER, "owner@example.com", INVITATION)

    assert message["To"] == "owner@example.com"
    assert message["From"] == get_settings().mail_from
    assert message["Subject"] == "Einladung zu Alpha Maschinenbau auf SeeDoc"
    text = _part(message, "plain")
    html_body = _part(message, "html")
    assert text.startswith("Guten Tag,")
    assert "http://localhost:5173/invite/abc" in text
    assert 'href="http://localhost:5173/invite/abc"' in html_body
    assert "{{" not in text + html_body
    assert "Mail template" not in html_body  # the documenting comment is not sent


def test_build_email_escapes_values_in_html_only() -> None:
    context = {**INVITATION, "tenant_name": 'Kraft & <script>"x"</script>'}

    message = build_email(MailTemplate.INVITATION_TENANT_MEMBER, "owner@example.com", context)

    assert "Kraft &amp; &lt;script&gt;&quot;x&quot;&lt;/script&gt;" in _part(message, "html")
    assert "<script>" not in _part(message, "html")
    assert 'Kraft & <script>"x"</script>' in _part(message, "plain")


def test_build_email_subject_cannot_carry_extra_headers() -> None:
    context = {**INVITATION, "tenant_name": "Evil\r\nBcc: victim@example.com"}

    message = build_email(MailTemplate.INVITATION_TENANT_MEMBER, "owner@example.com", context)

    assert message["Subject"] == "Einladung zu Evil Bcc: victim@example.com auf SeeDoc"
    assert message["Bcc"] is None


def test_build_email_missing_value_raises() -> None:
    with pytest.raises(KeyError, match="invitation_url"):
        build_email(MailTemplate.INVITATION_TENANT_MEMBER, "owner@example.com", {"tenant_name": "Alpha"})


def test_get_app_link_joins_app_url_and_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_URL", "https://app.seedoc.cloud/")
    get_settings.cache_clear()
    try:
        assert get_app_link("/invite/abc") == "https://app.seedoc.cloud/invite/abc"
    finally:
        get_settings.cache_clear()


def test_send_smtp_locally_uses_plain_smtp_without_login(fake_smtp: type[_FakeSmtp]) -> None:
    message = build_email(MailTemplate.PASSWORD_RESET, "user@example.com", {"reset_url": "http://x/reset-password/t"})

    _real_send_smtp(message)

    [smtp] = fake_smtp.created
    assert (smtp.host, smtp.port, smtp.context) == ("localhost", 1025, None)
    assert smtp.login_args is None
    assert smtp.sent == [message]


@pytest.mark.parametrize("port", [465, 2465])
def test_send_smtp_on_implicit_tls_ports_uses_tls_and_logs_in(
    monkeypatch: pytest.MonkeyPatch, fake_smtp: type[_FakeSmtp], port: int
) -> None:
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.resend.com")
    monkeypatch.setenv("MAIL_SMTP_PORT", str(port))
    monkeypatch.setenv("MAIL_SMTP_USER", "resend")
    monkeypatch.setenv("MAIL_API_KEY", "re_test_key")
    get_settings.cache_clear()
    message = build_email(MailTemplate.PASSWORD_RESET, "user@example.com", {"reset_url": "http://x/reset-password/t"})

    _real_send_smtp(message)

    [smtp] = fake_smtp.created
    assert (smtp.host, smtp.port) == ("smtp.resend.com", port)
    assert isinstance(smtp.context, ssl.SSLContext)
    assert smtp.context.verify_mode is ssl.CERT_REQUIRED
    assert smtp.login_args == ("resend", "re_test_key")
    assert smtp.sent == [message]


async def test_send_email_failure_is_logged_without_the_address(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_: EmailMessage) -> None:
        raise ConnectionRefusedError("user@example.com refused")

    monkeypatch.setattr(mail_send, "_send_smtp", refuse)

    with structlog.testing.capture_logs() as logs:
        send_email(MailTemplate.PASSWORD_RESET, "user@example.com", {"reset_url": "http://x/reset-password/t"})
        await send_pending_mail()  # does not raise

    assert logs == [
        {
            "event": "mail_send_failed",
            "template": "password_reset",
            "error": "ConnectionRefusedError",
            "log_level": "error",
        }
    ]
