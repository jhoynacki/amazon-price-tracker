"""
AES-256 encryption/decryption for sensitive fields (tokens, email).
Uses Fernet symmetric encryption from the cryptography package.
"""
import base64
import os
from cryptography.fernet import Fernet
from ..config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        settings = get_settings()
        key = settings.TOKEN_ENCRYPTION_KEY
        if not key:
            # Dev only: generate ephemeral key (tokens won't persist across restarts)
            key = Fernet.generate_key().decode()
        else:
            # Ensure it's valid Fernet key (32 url-safe base64 bytes)
            if len(key) < 44:
                raw = key.encode().ljust(32, b"=")[:32]
                key = base64.urlsafe_b64encode(raw).decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
