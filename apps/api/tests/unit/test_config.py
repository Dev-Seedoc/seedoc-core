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


def test_settings_production_accepts_complete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    for name in ("PIN_ENCRYPTION_KEY", "TOTP_ENCRYPTION_KEY", "IP_HASH_PEPPER"):
        monkeypatch.setenv(name, _KEY)
    for name in ("AI_API_KEY", "MAIL_API_KEY", "SENTRY_DSN"):
        monkeypatch.setenv(name, "set")

    assert _settings().is_production
