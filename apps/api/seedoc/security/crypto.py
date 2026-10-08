"""Hashing and symmetric encryption helpers."""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from seedoc.errors import AppError, ErrorCode

_NONCE_BYTES = 12


def get_ip_hash(ip: str, pepper: str) -> str:
    """sha256(IP_HASH_PEPPER || ip) as hex. The raw IP is never stored or logged (BUSINESS_RULES §5)."""
    return hashlib.sha256(pepper.encode() + ip.encode()).hexdigest()


def _aesgcm(key_b64: str) -> AESGCM:
    if not key_b64:
        # Allowed to be empty only locally (config.py); features that need the key fail here, loudly.
        raise AppError(ErrorCode.INTERNAL_ERROR, "encryption key is not configured")
    return AESGCM(base64.b64decode(key_b64))


def encrypt_secret(key_b64: str, plaintext: bytes) -> bytes:
    """AES-256-GCM with a random 12-byte nonce. Returns `nonce || ciphertext+tag` for a `bytea` column."""
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + _aesgcm(key_b64).encrypt(nonce, plaintext, None)


def decrypt_secret(key_b64: str, sealed: bytes) -> bytes:
    """Inverse of `encrypt_secret`. A wrong key or tampered data raises `internal_error` (never returns garbage)."""
    try:
        return _aesgcm(key_b64).decrypt(sealed[:_NONCE_BYTES], sealed[_NONCE_BYTES:], None)
    except InvalidTag as exc:
        raise AppError(ErrorCode.INTERNAL_ERROR, "stored secret cannot be decrypted") from exc
