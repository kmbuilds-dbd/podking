from functools import lru_cache

from cryptography.fernet import Fernet

from podking.config import get_settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode())


def decrypt(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()
