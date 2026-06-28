import os

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-unit")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("PINECONE_API_KEY", "test-key")
os.environ.setdefault("INDEX_NAME", "test-index")

from app.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestHashAndVerify:
    def test_hash_is_not_plaintext(self) -> None:
        hashed = hash_password("minha-senha")
        assert hashed != "minha-senha"

    def test_hash_is_reproducibly_verifiable(self) -> None:
        hashed = hash_password("segredo")
        assert verify_password("segredo", hashed) is True

    def test_wrong_password_fails_verification(self) -> None:
        hashed = hash_password("certa")
        assert verify_password("errada", hashed) is False

    def test_empty_password_can_be_hashed(self) -> None:
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_different_hashes_for_same_password(self) -> None:
        h1 = hash_password("abc")
        h2 = hash_password("abc")
        assert h1 != h2


class TestJWT:
    def test_create_token_returns_string(self) -> None:
        token = create_access_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_decode_returns_subject(self) -> None:
        token = create_access_token(subject="user-abc")
        subject = decode_access_token(token)
        assert subject == "user-abc"

    def test_token_with_email(self) -> None:
        token = create_access_token(subject="user-xyz", email="test@example.com")
        subject = decode_access_token(token)
        assert subject == "user-xyz"

    def test_invalid_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid authentication token"):
            decode_access_token("token.invalido.aqui")

    def test_tampered_token_raises_value_error(self) -> None:
        token = create_access_token(subject="user-1")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            decode_access_token(tampered)

    def test_empty_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            decode_access_token("")
