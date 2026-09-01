"""Credential encryption round-trip. Ciphertext must differ from plaintext and
decrypt back exactly. Runs without a browser/DB."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def test_crypto_roundtrip() -> None:
    os.environ["TESTPILOT_SECRET_KEY"] = Fernet.generate_key().decode()
    from app import crypto
    from app.config import get_settings

    get_settings.cache_clear()
    crypto._fernet.cache_clear()

    secret = '{"cookies":[{"name":"session","value":"s3cr3t"}]}'
    ct = crypto.encrypt(secret)
    assert ct != secret  # stored value is ciphertext, not plaintext
    assert "s3cr3t" not in ct
    assert crypto.decrypt(ct) == secret
    assert crypto.secret_configured() is True


if __name__ == "__main__":
    test_crypto_roundtrip()
    print("crypto self-check: OK")
