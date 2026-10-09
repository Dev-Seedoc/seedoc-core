"""Application settings (NAMING §10). The app refuses to start if a required var is missing."""

import base64
import binascii
from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class AiProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    MISTRAL = "mistral"


SECRET_KEY_BYTES = 32
_SECRET_FIELDS = ("pin_encryption_key", "totp_encryption_key", "ip_hash_pepper")
_REQUIRED_OUTSIDE_LOCAL = ("mail_api_key",)
# Staging runs without them until they exist (AI from M4, Sentry later); production never does.
_REQUIRED_IN_PRODUCTION = ("ai_api_key", "sentry_dsn")
SMTP_TLS_PORT = 465  # implicit TLS; the only port allowed outside local


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    environment: Environment
    app_url: str
    app_host: str

    database_url: str
    database_admin_url: str
    database_owner_url: str

    s3_endpoint: str
    s3_region: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str

    pin_encryption_key: str = ""
    totp_encryption_key: str = ""
    ip_hash_pepper: str = ""

    ai_provider: AiProvider = AiProvider.OPENAI
    ai_api_key: str = ""
    ai_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4.1-mini"

    # SMTP (ARCHITECTURE D20): Mailpit locally, Resend (`smtp.resend.com:465`, user `resend`) elsewhere.
    mail_smtp_host: str = "localhost"
    mail_smtp_port: int = 1025
    mail_smtp_user: str = ""
    mail_api_key: str = ""  # SMTP password (the Resend API key); empty for Mailpit
    mail_from: str = "SeeDoc <noreply@mail.seedoc.cloud>"

    sentry_dsn: str = ""

    feature_portal_pin: bool = True
    feature_operator_accounts: bool = True
    feature_exports: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @model_validator(mode="after")
    def _check_secrets(self) -> Self:
        is_local = self.environment is Environment.LOCAL
        for name in _SECRET_FIELDS:
            value: str = getattr(self, name)
            if not value:
                if is_local:
                    continue
                raise ValueError(f"{name.upper()} is required outside local")
            try:
                decoded = base64.b64decode(value, validate=True)
            except binascii.Error as exc:
                raise ValueError(f"{name.upper()} must be base64") from exc
            if len(decoded) != SECRET_KEY_BYTES:
                raise ValueError(f"{name.upper()} must decode to {SECRET_KEY_BYTES} bytes")
        if not is_local:
            required = _REQUIRED_OUTSIDE_LOCAL + (_REQUIRED_IN_PRODUCTION if self.is_production else ())
            missing = [name.upper() for name in required if not getattr(self, name)]
            if missing:
                raise ValueError(f"required in {self.environment.value}: {', '.join(missing)}")
            if self.mail_smtp_port != SMTP_TLS_PORT:
                raise ValueError(f"MAIL_SMTP_PORT must be {SMTP_TLS_PORT} (implicit TLS) outside local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the environment
