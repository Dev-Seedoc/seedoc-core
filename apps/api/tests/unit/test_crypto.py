import base64

import pytest

from seedoc.errors import AppError, ErrorCode
from seedoc.security.crypto import decrypt_secret, encrypt_secret

KEY = base64.b64encode(b"k" * 32).decode()
OTHER_KEY = base64.b64encode(b"o" * 32).decode()


def test_encrypt_secret_round_trip_with_random_nonce() -> None:
    first = encrypt_secret(KEY, b"JBSWY3DPEHPK3PXP")
    second = encrypt_secret(KEY, b"JBSWY3DPEHPK3PXP")

    assert first != second
    assert b"JBSWY3DPEHPK3PXP" not in first
    assert decrypt_secret(KEY, first) == b"JBSWY3DPEHPK3PXP"


def test_decrypt_secret_with_wrong_key_fails() -> None:
    sealed = encrypt_secret(KEY, b"secret")

    with pytest.raises(AppError) as error:
        decrypt_secret(OTHER_KEY, sealed)
    assert error.value.code is ErrorCode.INTERNAL_ERROR


def test_encrypt_secret_without_key_fails() -> None:
    with pytest.raises(AppError, match="not configured"):
        encrypt_secret("", b"secret")
