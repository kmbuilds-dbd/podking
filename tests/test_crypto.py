import pytest
from cryptography.fernet import InvalidToken

from podking.crypto import decrypt, encrypt


def test_encrypt_decrypt_roundtrip() -> None:
    original = "sk-ant-xxx-very-secret"
    encrypted = encrypt(original)
    assert isinstance(encrypted, bytes)
    assert encrypted != original.encode()
    assert decrypt(encrypted) == original


def test_encrypt_produces_different_output_each_call() -> None:
    a = encrypt("same")
    b = encrypt("same")
    assert a != b  # Fernet includes a timestamp + IV, so outputs differ
    assert decrypt(a) == decrypt(b) == "same"


def test_decrypt_rejects_tampered_blob() -> None:
    blob = encrypt("hello")
    tampered = blob[:-1] + bytes([(blob[-1] + 1) % 256])
    with pytest.raises(InvalidToken):
        decrypt(tampered)
