import base64

import pytest
from pydantic import ValidationError

from seedoc.config import Settings

_KEY = base64.b64encode(b"k" * 32).decode()


def _settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def test_settings_local_allows_empty_secrets() -> None:
    settings = _settings(PIN_ENCRYPTION_KEY="", TOTP_ENCRYPTION_KEY="", IP_HASH_PEPPER="")

    assert settings.pin_encryption_key == ""


def test_settings_production_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("PIN_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError, match="PIN_ENCRYPTION_KEY is required"):
        _settings()


def test_settings_rejects_short_key() -> None:
    with pytest.raises(ValidationError, match="must decode to 32 bytes"):
        _settings(PIN_ENCRYPTION_KEY=base64.b64encode(b"short").decode())


def _set_complete_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    for name in ("PIN_ENCRYPTION_KEY", "TOTP_ENCRYPTION_KEY", "IP_HASH_PEPPER"):
        monkeypatch.setenv(name, _KEY)
    for name in ("AI_API_KEY", "MAIL_API_KEY", "SENTRY_DSN"):
        monkeypatch.setenv(name, "set")
    monkeypatch.setenv("MAIL_SMTP_PORT", "465")


def test_settings_production_accepts_complete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)

    assert _settings().is_production


def test_settings_staging_runs_without_ai_and_sentry_but_not_without_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("SENTRY_DSN", "")

    assert _settings().environment == "staging"

    monkeypatch.setenv("MAIL_API_KEY", "")
    with pytest.raises(ValidationError, match="required in staging: MAIL_API_KEY"):
        _settings()


def test_settings_production_requires_ai_and_sentry(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "")

    with pytest.raises(ValidationError, match="required in production: SENTRY_DSN"):
        _settings()


def test_settings_production_accepts_resend_alternative_tls_port(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("MAIL_SMTP_PORT", "2465")  # Hetzner blocks outgoing 465

    assert _settings().mail_smtp_port == 2465


def test_settings_production_requires_implicit_tls_for_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_complete_production_env(monkeypatch)
    monkeypatch.setenv("MAIL_SMTP_PORT", "1025")

    with pytest.raises(ValidationError, match="MAIL_SMTP_PORT must be 465"):
        _settings()
