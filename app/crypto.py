"""Symmetric encryption for stored test credentials.

Secrets (login_state snapshots, robot-account passwords) are encrypted at rest with
a Fernet key from TESTPILOT_SECRET_KEY. Ciphertext is what lands in the DB; plaintext
only ever exists in memory inside the executor at injection time.

Generate a key:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


class SecretKeyMissing(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise SecretKeyMissing(
            "TESTPILOT_SECRET_KEY is not set — credential storage is disabled. "
            'Generate one: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def secret_configured() -> bool:
    return bool(get_settings().secret_key)
