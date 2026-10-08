"""TOTP for staff (ARCHITECTURE §8). The secret is stored encrypted with `TOTP_ENCRYPTION_KEY` (AES-256-GCM)."""

from urllib.parse import quote, urlencode

import pyotp

from seedoc.config import get_settings
from seedoc.security.crypto import decrypt_secret, encrypt_secret

TOTP_ISSUER = "SeeDoc"
TOTP_VALID_WINDOW = 1  # accept the previous and next 30-second step (clock drift)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> bytes:
    return encrypt_secret(get_settings().totp_encryption_key, secret.encode("ascii"))


def decrypt_totp_secret(sealed: bytes) -> str:
    return decrypt_secret(get_settings().totp_encryption_key, sealed).decode("ascii")


def get_totp_uri(secret: str, email: str) -> str:
    """`otpauth://` URI for authenticator apps (shown as a QR code by the staff screen).

    Built here (Key Uri Format: `otpauth://totp/<issuer>:<account>?secret=…&issuer=…`) instead of via
    `pyotp.TOTP.provisioning_uri`, whose untyped `**kwargs` would break strict type checking.
    """
    label = quote(f"{TOTP_ISSUER}:{email}", safe="@:")
    return f"otpauth://totp/{label}?{urlencode({'secret': secret, 'issuer': TOTP_ISSUER})}"


def verify_totp_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=TOTP_VALID_WINDOW)
